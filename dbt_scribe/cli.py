from __future__ import annotations

import sys
from pathlib import Path

import click

from dbt_scribe import __version__
from dbt_scribe.analyzer import Layer, build_enriched_model
from dbt_scribe.catalog import ci_gate
from dbt_scribe.catalog.catalog_parser import parse_catalog
from dbt_scribe.catalog.coverage_engine import CoverageResult, compute_coverage
from dbt_scribe.catalog.reporters import html_reporter, json_reporter, terminal_reporter
from dbt_scribe.config import ConfigError, ScribeConfig, load_config, resolve_provider
from dbt_scribe.generators.docs_generator import DocsResult, generate_docs
from dbt_scribe.generators.tests_generator import TestsResult, generate_tests
from dbt_scribe.parsers.manifest_parser import ManifestNode, parse_manifest
from dbt_scribe.parsers.yaml_parser import YamlModel, parse_yaml
from dbt_scribe.resolver import resolve_target
from dbt_scribe.writers.docs_writer import write_docs_block
from dbt_scribe.writers.yaml_writer import write_yaml

_REQUIRED_FILES = ["dbt_project.yml", "target/manifest.json", "dbt-scribe.yml"]

_DEFAULT_CONFIG = """\
version: 1

llm:
  provider: anthropic
  # model: claude-sonnet-4-6  # defaults to latest Sonnet (4.x generation, no date suffix)
  temperature: 0.2

docs:
  two_tier: true
  shared_columns:
    - created_at
    - updated_at
    - _fivetran_synced
  default_owner: "Data Team"
  default_contact: ""

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
  fail_on_threshold: false

catalog:
  report_path: target/dbt-scribe-catalog.html
  open_after_generate: false
  include_catalog: true
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
    _run_catalog(
        target=target,
        output="terminal",
        report_path=None,
        threshold_docs=None,
        threshold_tests=None,
        ci=False,
        output_format="table",
        layer=None,
    )


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to audit.")
@click.option(
    "--output",
    "output",
    type=click.Choice(["terminal", "html", "json"], case_sensitive=False),
    default="terminal",
    show_default=True,
    help="Report output destination/format.",
)
@click.option(
    "--report-path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Path for --output html.",
)
@click.option("--threshold-docs", type=float, default=None, help="Override doc threshold.")
@click.option("--threshold-tests", type=float, default=None, help="Override test threshold.")
@click.option("--ci", is_flag=True, help="Exit with code 1 when thresholds fail.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Backward-compatible output format alias.",
)
@click.option("--layer", default=None, help="Only include one layer: staging, intermediate, marts.")
def catalog(
    target: str,
    output: str,
    report_path: Path | None,
    threshold_docs: float | None,
    threshold_tests: float | None,
    ci: bool,
    output_format: str,
    layer: str | None,
) -> None:
    """Generate documentation and test coverage reports."""
    _run_catalog(
        target=target,
        output=output.lower(),
        report_path=report_path,
        threshold_docs=threshold_docs,
        threshold_tests=threshold_tests,
        ci=ci,
        output_format=output_format.lower(),
        layer=layer,
    )


def _load_project(
    target: str,
    *,
    check_api_key: bool = True,
) -> tuple[ScribeConfig, list[ManifestNode]]:
    try:
        _bootstrap()
        model_root = _read_model_root()
        config = load_config("dbt-scribe.yml", check_api_key=check_api_key, model_root=model_root)
        nodes = resolve_target(target, parse_manifest("target/manifest.json"), model_root=model_root)
    except (BootstrapError, ValueError, ConfigError) as exc:
        raise click.ClickException(str(exc)) from exc
    return config, nodes


def _run_catalog(
    *,
    target: str,
    output: str,
    report_path: Path | None,
    threshold_docs: float | None,
    threshold_tests: float | None,
    ci: bool,
    output_format: str,
    layer: str | None,
) -> None:
    config, nodes = _load_project(target, check_api_key=False)
    config = _config_with_threshold_overrides(
        config,
        threshold_docs=threshold_docs,
        threshold_tests=threshold_tests,
    )
    result = _compute_catalog_result(config, nodes, layer_filter=layer)
    resolved_output = "json" if output_format == "json" else output

    if resolved_output == "json":
        click.echo(json_reporter.render(result), nl=False)
    elif resolved_output == "html":
        destination = report_path or Path(config.catalog.report_path)
        html_reporter.render(result, destination)
        click.echo(f"HTML report written to {destination}")
    else:
        terminal_reporter.render(result)

    ci_mode = ci or config.coverage.fail_on_threshold
    if ci_mode:
        exit_code = ci_gate.check(result, ci_mode=True)
        if exit_code:
            click.echo(ci_gate.format_failure_message(result), err=True)
        sys.exit(exit_code)


def _config_with_threshold_overrides(
    config: ScribeConfig,
    *,
    threshold_docs: float | None,
    threshold_tests: float | None,
) -> ScribeConfig:
    if threshold_docs is None and threshold_tests is None:
        return config

    coverage_updates = {}
    if threshold_docs is not None:
        coverage_updates["min_doc_coverage"] = threshold_docs
    if threshold_tests is not None:
        coverage_updates["min_test_coverage"] = threshold_tests

    return config.model_copy(
        update={"coverage": config.coverage.model_copy(update=coverage_updates)}
    )


def _compute_catalog_result(
    config: ScribeConfig,
    nodes: list[ManifestNode],
    *,
    layer_filter: str | None,
) -> CoverageResult:
    catalog = (
        parse_catalog(Path("target/catalog.json"))
        if config.catalog.include_catalog
        else None
    )
    yaml_models = _yaml_models_for_nodes(nodes, config)
    result = compute_coverage(nodes, catalog, yaml_models, config)
    return _filter_result_by_layer(result, layer_filter)


def _yaml_models_for_nodes(
    nodes: list[ManifestNode],
    config: ScribeConfig,
) -> dict[str, YamlModel | None]:
    return {
        node.name: parse_yaml(Path(config.model_root) / Path(node.path).with_suffix(".yml"))
        for node in nodes
    }


def _filter_result_by_layer(result: CoverageResult, layer_filter: str | None) -> CoverageResult:
    if layer_filter is None:
        return result

    layer = _layer_from_filter(layer_filter)
    return CoverageResult(
        generated_at=result.generated_at,
        project_name=result.project_name,
        adapter=result.adapter,
        dbt_scribe_version=result.dbt_scribe_version,
        thresholds=result.thresholds,
        layers=[item for item in result.layers if item.layer is layer],
    )


def _layer_from_filter(layer_filter: str) -> Layer:
    try:
        return Layer(layer_filter.lower())
    except ValueError:
        return Layer.UNKNOWN


def _read_model_root() -> str:
    import yaml as _yaml

    try:
        raw = _yaml.safe_load(Path("dbt_project.yml").read_text()) or {}
    except Exception:
        return "models"
    paths = raw.get("model-paths") or raw.get("source-paths")
    if isinstance(paths, list) and paths:
        return paths[0]
    return "models"


def _build_model(
    node: ManifestNode,
    config: ScribeConfig,
    *,
    overwrite_existing: bool = False,
):
    yaml_path = Path(config.model_root) / Path(node.path).with_suffix(".yml")
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
