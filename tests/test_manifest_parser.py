from pathlib import Path

from dbt_scribe.parsers.manifest_parser import ManifestColumn, ManifestNode, parse_manifest

FIXTURE_MANIFEST = (
    Path(__file__).parent / "fixtures" / "dbt_project" / "target" / "manifest.json"
)


def test_parse_manifest_returns_model_nodes_only():
    nodes = parse_manifest(FIXTURE_MANIFEST)

    # 4 nodes: 3 original DuckDB nodes + 1 BigQuery regression fixture (stg_bq__orders)
    assert len(nodes) == 4
    assert all(isinstance(node, ManifestNode) for node in nodes)
    assert {node.resource_type for node in nodes} == {"model"}


def test_parse_manifest_extracts_compiled_sql():
    nodes = parse_manifest(FIXTURE_MANIFEST)
    staging_node = next(node for node in nodes if node.name == "stg_api_sports__fixtures")

    assert "select * from renamed" in staging_node.compiled_code
    assert "{{" not in staging_node.compiled_code


def test_parse_manifest_extracts_columns():
    nodes = parse_manifest(FIXTURE_MANIFEST)
    staging_node = next(node for node in nodes if node.name == "stg_api_sports__fixtures")

    assert staging_node.columns["fixture_id"] == ManifestColumn(
        name="fixture_id",
        data_type="integer",
        description="",
    )
    assert staging_node.columns["is_finished"].data_type == "boolean"


def test_parse_manifest_extracts_fqn_lineage_config_path_and_adapter():
    nodes = parse_manifest(FIXTURE_MANIFEST)
    mart_node = next(node for node in nodes if node.name == "fixtures")

    assert mart_node.unique_id == "model.fixture_project.fixtures"
    assert mart_node.fqn == ["fixture_project", "marts", "rugby", "fixtures"]
    assert mart_node.depends_on_nodes == [
        "model.fixture_project.int_fixtures_enriched_with_teams"
    ]
    assert mart_node.tags == []
    assert mart_node.materialized == "table"
    assert mart_node.path == "marts/rugby/fixtures.sql"
    assert mart_node.adapter_type == "duckdb"