from __future__ import annotations

import os
from pathlib import Path

import click

from dbt_scribe import __version__

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
    try:
        _bootstrap()
    except BootstrapError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.ClickException("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing tests.")
def tests(target: str, dry_run: bool, force: bool) -> None:
    """Generate generic YAML tests."""
    try:
        _bootstrap()
    except BootstrapError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.ClickException("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing documentation and tests.")
def generate(target: str, dry_run: bool, force: bool) -> None:
    """Generate documentation and tests in one pass."""
    try:
        _bootstrap()
    except BootstrapError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.ClickException("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to audit.")
def audit(target: str) -> None:
    """Show documentation and test coverage report."""
    try:
        _bootstrap()
    except BootstrapError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.ClickException("not yet implemented")
