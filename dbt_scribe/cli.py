import click

from dbt_scribe import __version__


@click.group()
@click.version_option(__version__, prog_name="dbt-scribe")
def cli() -> None:
    """LLM-powered documentation and test generation for dbt Core projects."""


@cli.command()
def init() -> None:
    """Generate a dbt-scribe.yml config in the current dbt project."""
    raise NotImplementedError("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing descriptions.")
def docs(target: str, dry_run: bool, force: bool) -> None:
    """Generate model and column documentation."""
    raise NotImplementedError("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing tests.")
def tests(target: str, dry_run: bool, force: bool) -> None:
    """Generate generic YAML tests."""
    raise NotImplementedError("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to process.")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files.")
@click.option("--force", is_flag=True, help="Overwrite existing documentation and tests.")
def generate(target: str, dry_run: bool, force: bool) -> None:
    """Generate documentation and tests in one pass."""
    raise NotImplementedError("not yet implemented")


@cli.command()
@click.option("--target", default="models/", help="File, directory, or project root to audit.")
def audit(target: str) -> None:
    """Show documentation and test coverage report."""
    raise NotImplementedError("not yet implemented")
