from __future__ import annotations

import shutil
from pathlib import Path

from ruamel.yaml import YAML

from dbt_scribe.analyzer import build_enriched_model
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult
from dbt_scribe.parsers.manifest_parser import parse_manifest
from dbt_scribe.parsers.yaml_parser import parse_yaml
from dbt_scribe.writers.yaml_writer import write_yaml

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


def _load_yaml(path: Path):
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


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

    written = _load_yaml(project / "models" / "marts" / "rugby" / "fixtures.yml")
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

    written = _load_yaml(
        project / "models" / "staging" / "api_sports" / "stg_api_sports__fixtures.yml"
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

    written = _load_yaml(
        project / "models" / "staging" / "api_sports" / "stg_api_sports__fixtures.yml"
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


def test_write_yaml_with_source_path_merges_shared_file_without_overwriting_other_models(
    tmp_path,
    monkeypatch,
):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "int_fixtures_enriched_with_teams")
    shared_yaml = project / "models" / "intermediate" / "_intermediate__models.yml"
    shared_yaml.write_text(
        """\
version: 2
models:
  - name: other_intermediate_model
    description: Keep me.
    columns:
      - name: other_id
        description: Other identifier.
  - name: int_fixtures_enriched_with_teams
    description: ""
    columns:
      - name: fixture_id
        description: ""
""",
        encoding="utf-8",
    )

    result = write_yaml(
        model,
        DocsResult(
            model_description="Generated shared model docs.",
            docs_block_content="Long docs",
            columns={"fixture_id": "Generated fixture id."},
        ),
        TestsResult(columns={"fixture_id": ["not_null"]}),
        _config(),
        dry_run=False,
        source_path=shared_yaml,
    )

    written = _load_yaml(shared_yaml)
    models = {model_yaml["name"]: model_yaml for model_yaml in written["models"]}
    columns = {
        column["name"]: column for column in models["int_fixtures_enriched_with_teams"]["columns"]
    }
    assert result.path == shared_yaml.resolve()
    assert models["other_intermediate_model"]["description"] == "Keep me."
    assert models["other_intermediate_model"]["columns"][0]["description"] == "Other identifier."
    assert models["int_fixtures_enriched_with_teams"]["description"] == (
        "Generated shared model docs."
    )
    assert columns["fixture_id"]["description"] == "Generated fixture id."
    assert columns["fixture_id"]["data_tests"] == ["not_null"]


def test_write_yaml_with_source_path_none_falls_back_to_per_model_file(
    tmp_path,
    monkeypatch,
):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")
    target = project / "models" / "marts" / "rugby" / "fixtures.yml"

    result = write_yaml(
        model,
        DocsResult("Generated marts docs.", "Long docs", {}),
        TestsResult(columns={}),
        _config(),
        dry_run=False,
        source_path=None,
    )

    assert result.path == target.resolve()
    assert target.exists()


def test_write_yaml_preserves_comments_in_existing_shared_file(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "int_fixtures_enriched_with_teams")
    shared_yaml = project / "models" / "intermediate" / "_intermediate__models.yml"
    shared_yaml.write_text(
        """\
version: 2
models:
  # Existing shared model comment
  - name: int_fixtures_enriched_with_teams
    description: ""
    columns:
      - name: fixture_id # keep inline column comment
        description: ""
""",
        encoding="utf-8",
    )

    write_yaml(
        model,
        DocsResult(
            model_description="Generated shared model docs.",
            docs_block_content="Long docs",
            columns={"fixture_id": "Generated fixture id."},
        ),
        TestsResult(columns={}),
        _config(),
        dry_run=False,
        source_path=shared_yaml,
    )

    content = shared_yaml.read_text(encoding="utf-8")
    assert "# Existing shared model comment" in content
    assert "# keep inline column comment" in content


def test_write_yaml_adds_todo_comment_to_empty_accepted_values(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "stg_api_sports__fixtures", with_yaml=True)

    write_yaml(
        model,
        DocsResult(
            model_description="Generated model description.",
            docs_block_content="Long docs",
            columns={},
        ),
        TestsResult(
            columns={
                "fixture_status": [
                    {
                        "accepted_values": {
                            "name": "stg_api_sports__fixtures_fixture_status_accepted_values",
                            "arguments": {"values": []},
                        }
                    }
                ]
            }
        ),
        _config(),
        dry_run=False,
    )

    content = (
        project / "models" / "staging" / "api_sports" / "stg_api_sports__fixtures.yml"
    ).read_text(encoding="utf-8")
    assert "values: []  # TODO: fill with actual enum values from source system" in content
