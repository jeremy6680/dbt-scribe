from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from dbt_scribe.cli import cli
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


class FakeProvider:
    pass


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "dbt_project"
    shutil.copytree(FIXTURE_PROJECT, project)
    return project


def _patch_pipeline(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("dbt_scribe.cli.resolve_provider", lambda config: FakeProvider())
    monkeypatch.setattr(
        "dbt_scribe.cli.generate_docs",
        lambda model, provider, config: DocsResult(
            model_description=f"Generated docs for {model.name}.",
            docs_block_content=f"Long docs for {model.name}.",
            columns={column_name: f"Generated description for {column_name}." for column_name in model.columns},
        ),
    )
    monkeypatch.setattr(
        "dbt_scribe.cli.generate_tests",
        lambda model, provider, config: TestsResult(
            columns={
                "fixture_id": [
                    {"not_null": {"name": f"not_null_{model.name}_fixture_id"}},
                    {"unique": {"name": f"unique_{model.name}_fixture_id"}},
                ]
            }
        ),
    )


def test_docs_command_runs_pipeline_and_writes_yaml_and_docs(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _patch_pipeline(monkeypatch)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["docs", "--target", "models/marts/rugby/fixtures.sql"])

    assert result.exit_code == 0, result.output
    assert "docs: fixtures" in result.output
    assert (project / "models" / "marts" / "rugby" / "fixtures.yml").exists()
    assert (project / "models" / "marts" / "rugby" / "_rugby__docs.md").exists()


def test_tests_command_writes_yaml_tests_only(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _patch_pipeline(monkeypatch)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["tests", "--target", "models/marts/rugby"])

    assert result.exit_code == 0, result.output
    assert "tests: fixtures" in result.output
    yaml_content = (project / "models" / "marts" / "rugby" / "fixtures.yml").read_text()
    assert "not_null_fixtures_fixture_id" in yaml_content
    assert not (project / "models" / "marts" / "rugby" / "_rugby__docs.md").exists()


def test_generate_command_runs_docs_and_tests(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _patch_pipeline(monkeypatch)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["generate", "--target", "models/marts/rugby"])

    assert result.exit_code == 0, result.output
    assert "generate: fixtures" in result.output
    assert "not_null_fixtures_fixture_id" in (
        project / "models" / "marts" / "rugby" / "fixtures.yml"
    ).read_text()
    assert "Long docs for fixtures." in (
        project / "models" / "marts" / "rugby" / "_rugby__docs.md"
    ).read_text()


def test_generate_dry_run_does_not_write(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _patch_pipeline(monkeypatch)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(
            cli,
            ["generate", "--target", "models/marts/rugby", "--dry-run"],
        )

    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert not (project / "models" / "marts" / "rugby" / "fixtures.yml").exists()
    assert not (project / "models" / "marts" / "rugby" / "_rugby__docs.md").exists()


def test_docs_force_overwrites_existing_descriptions(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _patch_pipeline(monkeypatch)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(
            cli,
            [
                "docs",
                "--target",
                "models/staging/api_sports/stg_api_sports__fixtures.sql",
                "--force",
            ],
        )

    assert result.exit_code == 0, result.output
    yaml_content = (
        project
        / "models"
        / "staging"
        / "api_sports"
        / "stg_api_sports__fixtures.yml"
    ).read_text()
    assert "Generated description for fixture_id." in yaml_content


def test_audit_command_reports_coverage(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["audit", "--target", "models/staging"])

    assert result.exit_code == 0, result.output
    assert "Audit summary" in result.output
    assert "stg_api_sports__fixtures" in result.output
    assert "doc coverage" in result.output
