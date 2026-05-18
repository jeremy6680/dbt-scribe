from __future__ import annotations

import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from dbt_scribe.cli import cli

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "dbt_project"
    shutil.copytree(FIXTURE_PROJECT, project)
    return project


def test_catalog_command_runs_without_error_on_fixture_project(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog"])

    assert result.exit_code == 0, result.output
    assert "dbt-scribe catalog" in result.output
    assert "fixture_project" in result.output


def test_audit_alias_matches_catalog_terminal_output(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        audit_result = CliRunner().invoke(cli, ["audit", "--target", "models/staging"])
        catalog_result = CliRunner().invoke(
            cli,
            [
                "catalog",
                "--target",
                "models/staging",
                "--output",
                "terminal",
                "--format",
                "table",
            ],
        )

    assert audit_result.exit_code == 0, audit_result.output
    assert catalog_result.exit_code == 0, catalog_result.output
    assert audit_result.output == catalog_result.output


def test_catalog_ci_flag_returns_one_when_thresholds_fail(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog", "--ci"])

    assert result.exit_code == 1
    assert "Coverage thresholds failed:" in result.output


def test_catalog_ci_flag_returns_zero_when_threshold_overrides_pass(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(
            cli,
            [
                "catalog",
                "--ci",
                "--threshold-docs",
                "0",
                "--threshold-tests",
                "0",
            ],
        )

    assert result.exit_code == 0, result.output


def test_catalog_enforces_fail_on_threshold_config(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    config_path = project / "dbt-scribe.yml"
    config_path.write_text(
        config_path.read_text().replace("fail_on_threshold: false", "fail_on_threshold: true")
    )

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog"])

    assert result.exit_code == 1
    assert "Coverage thresholds failed:" in result.output


def test_catalog_output_html_creates_file_at_default_path(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    report_path = project / "target" / "dbt-scribe-catalog.html"

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog", "--output", "html"])

    assert result.exit_code == 0, result.output
    assert report_path.exists()
    assert "HTML report written to target/dbt-scribe-catalog.html" in result.output


def test_catalog_output_html_respects_report_path(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    report_path = project / "reports" / "catalog.html"

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(
            cli,
            ["catalog", "--output", "html", "--report-path", str(report_path)],
        )

    assert result.exit_code == 0, result.output
    assert report_path.exists()


def test_catalog_output_json_prints_valid_json(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog", "--output", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["project"] == "fixture_project"
    assert "global" in payload


def test_catalog_format_json_prints_valid_json(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["project"] == "fixture_project"


def test_catalog_layer_staging_filters_terminal_output(tmp_path, monkeypatch) -> None:
    project = _copy_project(tmp_path)

    with monkeypatch.context() as context:
        context.chdir(project)
        result = CliRunner().invoke(cli, ["catalog", "--layer", "staging"])

    assert result.exit_code == 0, result.output
    assert "STAGING" in result.output
    assert "INTERMEDIATE" not in result.output
    assert "MARTS" not in result.output
    assert "stg_api_sports__fixtures" in result.output
    assert "int_fixtures_enriched_with_teams" not in result.output
