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


def test_generate_dry_run_runs_full_fixture_pipeline_without_writes(tmp_path, monkeypatch):
    project = tmp_path / "dbt_project"
    shutil.copytree(FIXTURE_PROJECT, project)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("dbt_scribe.cli.resolve_provider", lambda config: FakeProvider())
    monkeypatch.setattr(
        "dbt_scribe.cli.generate_docs",
        lambda model, provider, config: DocsResult(
            model_description=f"Generated docs for {model.name}.",
            docs_block_content=f"Long docs for {model.name}.",
            columns={column_name: f"Description for {column_name}." for column_name in model.columns},
        ),
    )
    monkeypatch.setattr(
        "dbt_scribe.cli.generate_tests",
        lambda model, provider, config: TestsResult(columns={}),
    )

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["generate", "--target", "models/", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Summary: generate processed 3 model(s) (dry-run)." in result.output
    assert not (project / "models" / "marts" / "rugby" / "fixtures.yml").exists()
    assert not (project / "models" / "marts" / "rugby" / "_rugby__docs.md").exists()
