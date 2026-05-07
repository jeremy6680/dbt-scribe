from pathlib import Path

from dbt_scribe.parsers.manifest_parser import parse_manifest
from dbt_scribe.resolver import resolve_target

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"
FIXTURE_MANIFEST = FIXTURE_PROJECT / "target" / "manifest.json"


def _nodes():
    return parse_manifest(FIXTURE_MANIFEST)


def test_resolve_target_project_root_returns_all_models():
    nodes = resolve_target(".", _nodes())

    assert {node.name for node in nodes} == {
        "stg_api_sports__fixtures",
        "int_fixtures_enriched_with_teams",
        "fixtures",
    }


def test_resolve_target_directory_filters_by_model_path():
    nodes = resolve_target("models/staging", _nodes())

    assert [node.name for node in nodes] == ["stg_api_sports__fixtures"]


def test_resolve_target_file_matches_sql_or_yaml_path():
    nodes = _nodes()

    assert [
        node.name
        for node in resolve_target(
            "models/staging/api_sports/stg_api_sports__fixtures.sql",
            nodes,
        )
    ] == ["stg_api_sports__fixtures"]
    assert [
        node.name
        for node in resolve_target(
            "models/staging/api_sports/stg_api_sports__fixtures.yml",
            nodes,
        )
    ] == ["stg_api_sports__fixtures"]


def test_resolve_target_raises_for_no_matches():
    try:
        resolve_target("models/unknown", _nodes())
    except ValueError as exc:
        assert "No manifest model nodes matched" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
