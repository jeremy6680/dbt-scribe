from __future__ import annotations

from pathlib import Path

import click

from dbt_scribe import __version__
from dbt_scribe.analyzer import build_enriched_model
from dbt_scribe.config import ScribeConfig, load_config, resolve_provider
from dbt_scribe.generators.docs_generator import DocsResult, generate_docs
from dbt_scribe.generators.tests_generator import TestsResult, generate_tests
from dbt_scribe.parsers.manifest_parser import ManifestNode, parse_manifest
from dbt_scribe.parsers.yaml_parser import is_description_set, parse_yaml
from dbt_scribe.resolver import resolve_target
from dbt_scribe.writers.docs_writer import write_docs_block
from dbt_scribe.writers.yaml_writer import write_yaml

_REQUIRED_FILES = ["dbt_project.yml", "target/manifest.json", "dbt-scribe.yml"]

_DEFAULT_CONFIG = """\
version: 1

llm:
  provider: anthropic
  # model: claude-sonnet-4-20250514  # defaults to latest Sonnet
  temperature: 0.2

docs:
  two_tier: true
  shared_columns:
    - created_at
    - updated_at
    - _fivetran_synced
  default_owner: "Data Team"

tests:
  pk_patterns:
    - "^.*_id$"
    - "^id$"
  fk_patterns:
    - "^.*_fk$"
  enum_patterns:
    - "^.*_type$"
    - "^.*_status$"
    - "^.*_category$"

conventions:
  staging_prefix: staging
  intermediate_prefix: intermediate
  marts_prefix: marts

coverage:
  min_doc_coverage: 80
  min_test_coverage: 70
"""


class BootstrapError(Exception):
    pass


def _bootstrap(cwd: Path | None = None) -> None:
    root = cwd or Path.cwd()
    missing = [f for f in _REQUIRED_FILES if not (root / f).exists()]
    if not missing:
        return
    hints = {
        "dbt_project.yml": "Are you in the dbt project root directory?",
        "target/manifest.json": "Run 'dbt compile' to generate the manifest.",
        "dbt-scribe.yml": "Run 'dbt-scribe init' to create the configuration file.",
    }
    lines = ["Bootstrap check failed. Missing files:"]
    for f in missing:
        lines.append(f"  • {f}  →  {hints[f]}")
    raise BootstrapError("\n".join(lines))


@click.group()
@click.version_option(__version__, prog_name="dbt-scribe")
def cli() -> None:
    """LLM-powered documentation and test generation for dbt Core projects."""


@cli.command()
def init() -> None:
    """Generate a dbt-scribe.yml config in the current dbt project."""
    root = Path.cwd()
    if not (root / "dbt_project.yml").exists():
        raise click.ClickException(
            "dbt_project.yml not found. Are you in the dbt project root directory?"
        )
    config_path = root / "dbt-scribe.yml"
    if config_path.exists():
        raise click.ClickException(
            "dbt-scribe.yml already exists. Remove it first or edit it directly."
        )
    config_path.write_text(_DEFAULT_CONFIG)
    click.echo(f"Created {config_path}")
    click.echo("Edit dbt-scribe.yml to set your LLM provider and project conventions.")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing descriptions.")
def docs(target: str, dry_run: bool, force: bool) -> None:
    """Generate model and column documentation."""
    config, nodes = _load_project(target)
    provider = resolve_provider(config)
    for node in nodes:
        model = _build_model(node, config, overwrite_existing=force)
        docs_result = generate_docs(model, provider, config)
        yaml_result = write_yaml(
            model,
            docs_result,
            TestsResult(columns={}),
            config,
            dry_run,
            force=force,
        )
        docs_block_result = write_docs_block(model, docs_result, config, dry_run)
        _echo_status("docs", model.name, dry_run, yaml_result.changed or docs_block_result.changed)
    _echo_summary("docs", nodes, dry_run)


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing tests.")
def tests(target: str, dry_run: bool, force: bool) -> None:
    """Generate generic YAML tests."""
    config, nodes = _load_project(target)
    provider = resolve_provider(config)
    for node in nodes:
        model = _build_model(node, config, overwrite_existing=force)
        tests_result = generate_tests(model, provider, config)
        yaml_result = write_yaml(
            model,
            DocsResult(model_description=model.description or "", docs_block_content="", columns={}),
            tests_result,
            config,
            dry_run,
            force=force,
        )
        _echo_status("tests", model.name, dry_run, yaml_result.changed)
    _echo_summary("tests", nodes, dry_run)


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing documentation and tests.")
def generate(target: str, dry_run: bool, force: bool) -> None:
    """Generate documentation and tests in one pass."""
    config, nodes = _load_project(target)
    provider = resolve_provider(config)
    for node in nodes:
        model = _build_model(node, config, overwrite_existing=force)
        docs_result = generate_docs(model, provider, config)
        tests_result = generate_tests(model, provider, config)
        yaml_result = write_yaml(
            model,
            docs_result,
            tests_result,
            config,
            dry_run,
            force=force,
        )
        docs_block_result = write_docs_block(model, docs_result, config, dry_run)
        _echo_status("generate", model.name, dry_run, yaml_result.changed or docs_block_result.changed)
    _echo_summary("generate", nodes, dry_run)


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to audit.")
def audit(target: str) -> None:
    """Show documentation and test coverage report."""
    config, nodes = _load_project(target, check_api_key=False)
    click.echo("Audit summary")
    for node in nodes:
        model = _build_model(node, config)
        total_columns = len(model.columns)
        documented_columns = sum(
            1 for column in model.columns.values() if is_description_set(column.description)
        )
        tested_columns = sum(1 for column in model.columns.values() if column.tests)
        doc_coverage = _percentage(documented_columns, total_columns)
        test_coverage = _percentage(tested_columns, total_columns)
        click.echo(
            f"- {model.name}: doc coverage {doc_coverage}% "
            f"({documented_columns}/{total_columns}), test coverage {test_coverage}% "
            f"({tested_columns}/{total_columns})"
        )


def _load_project(
    target: str,
    *,
    check_api_key: bool = True,
) -> tuple[ScribeConfig, list[ManifestNode]]:
    try:
        _bootstrap()
        config = load_config("dbt-scribe.yml", check_api_key=check_api_key)
        nodes = resolve_target(target, parse_manifest("target/manifest.json"))
    except (BootstrapError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    return config, nodes


def _build_model(
    node: ManifestNode,
    config: ScribeConfig,
    *,
    overwrite_existing: bool = False,
):
    yaml_path = Path("models") / Path(node.path).with_suffix(".yml")
    yaml_model = parse_yaml(yaml_path)
    return build_enriched_model(
        node,
        yaml_model,
        config,
        overwrite_existing=overwrite_existing,
    )


def _echo_status(command: str, model_name: str, dry_run: bool, changed: bool) -> None:
    mode = "dry-run" if dry_run else "write"
    status = "changed" if changed else "unchanged"
    click.echo(f"{command}: {model_name} [{mode}, {status}]")


def _echo_summary(command: str, nodes: list[ManifestNode], dry_run: bool) -> None:
    suffix = " (dry-run)" if dry_run else ""
    click.echo(f"Summary: {command} processed {len(nodes)} model(s){suffix}.")


def _percentage(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 100
    return round((numerator / denominator) * 100)
