from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from dbt_scribe.analyzer import build_enriched_model
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult
from dbt_scribe.parsers.manifest_parser import parse_manifest
from dbt_scribe.parsers.yaml_parser import parse_yaml
from dbt_scribe.writers.yaml_writer import write_yaml

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


def _config() -> ScribeConfig:
    return ScribeConfig.model_construct(
        llm=None,
        docs=ScribeConfig.model_fields["docs"].default,
        tests=ScribeConfig.model_fields["tests"].default,
        coverage=ScribeConfig.model_fields["coverage"].default,
        conventions=ScribeConfig.model_fields["conventions"].default,
        cache=ScribeConfig.model_fields["cache"].default,
        version=1,
    )


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "dbt_project"
    shutil.copytree(FIXTURE_PROJECT, project)
    return project


def _model(project: Path, name: str, *, with_yaml: bool = False):
    manifest_node = next(
        node for node in parse_manifest(project / "target" / "manifest.json") if node.name == name
    )
    yaml_model = None
    if with_yaml:
        yaml_model = parse_yaml(project / "models" / manifest_node.path.replace(".sql", ".yml"))
    return build_enriched_model(manifest_node, yaml_model, _config())


def test_write_yaml_creates_missing_file_from_scratch(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")

    result = write_yaml(
        model,
        DocsResult(
            model_description="Curated rugby fixtures mart.",
            docs_block_content="Long docs",
            columns={"fixture_id": "Fixture identifier.", "fixture_status": "Fixture status."},
        ),
        TestsResult(
            columns={
                "fixture_id": [
                    {"not_null": {"name": "not_null_fixtures_fixture_id"}},
                    {"unique": {"name": "unique_fixtures_fixture_id"}},
                ]
            }
        ),
        _config(),
        dry_run=False,
    )

    written = yaml.safe_load((project / "models" / "marts" / "rugby" / "fixtures.yml").read_text())
    assert result.changed is True
    assert written["version"] == 2
    model_yaml = written["models"][0]
    assert model_yaml["name"] == "fixtures"
    assert model_yaml["description"] == "Curated rugby fixtures mart."
    assert model_yaml["columns"][0]["name"] == "fixture_id"
    assert model_yaml["columns"][0]["description"] == "Fixture identifier."
    assert model_yaml["columns"][0]["data_tests"] == [
        {"not_null": {"name": "not_null_fixtures_fixture_id"}},
        {"unique": {"name": "unique_fixtures_fixture_id"}},
    ]


def test_write_yaml_merges_without_force_preserving_existing_descriptions_and_tests(
    tmp_path,
    monkeypatch,
):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "stg_api_sports__fixtures", with_yaml=True)

    write_yaml(
        model,
        DocsResult(
            model_description="Generated model description.",
            docs_block_content="Long docs",
            columns={
                "fixture_id": "Generated fixture id.",
                "league_id": "Generated league id.",
            },
        ),
        TestsResult(columns={"fixture_id": ["accepted_values"]}),
        _config(),
        dry_run=False,
    )

    written = yaml.safe_load(
        (
            project
            / "models"
            / "staging"
            / "api_sports"
            / "stg_api_sports__fixtures.yml"
        ).read_text()
    )
    columns = {column["name"]: column for column in written["models"][0]["columns"]}
    assert columns["fixture_id"]["description"] == "{{ doc('fixture_id') }}"
    assert columns["fixture_id"]["data_tests"] == ["not_null", "unique", "accepted_values"]
    assert columns["league_id"]["description"] == "Generated league id."


def test_write_yaml_merges_with_force_overwriting_descriptions(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "stg_api_sports__fixtures", with_yaml=True)

    write_yaml(
        model,
        DocsResult(
            model_description="Generated model description.",
            docs_block_content="Long docs",
            columns={"fixture_id": "Generated fixture id."},
        ),
        TestsResult(columns={}),
        _config(),
        dry_run=False,
        force=True,
    )

    written = yaml.safe_load(
        (
            project
            / "models"
            / "staging"
            / "api_sports"
            / "stg_api_sports__fixtures.yml"
        ).read_text()
    )
    columns = {column["name"]: column for column in written["models"][0]["columns"]}
    assert columns["fixture_id"]["description"] == "Generated fixture id."


def test_write_yaml_dry_run_does_not_write_file(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")
    target = project / "models" / "marts" / "rugby" / "fixtures.yml"

    result = write_yaml(
        model,
        DocsResult("Generated", "Long docs", {}),
        TestsResult(columns={}),
        _config(),
        dry_run=True,
    )

    assert result.changed is True
    assert target.exists() is False
