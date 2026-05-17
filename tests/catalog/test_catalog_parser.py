import json
from pathlib import Path

import pytest

from dbt_scribe.catalog.catalog_parser import (
    CatalogColumn,
    CatalogNode,
    parse_catalog,
)

FIXTURE_CATALOG = (
    Path(__file__).parent.parent
    / "fixtures"
    / "dbt_project"
    / "target"
    / "catalog.json"
)


def test_parse_catalog_returns_none_when_file_absent(tmp_path: Path) -> None:
    missing_catalog = tmp_path / "catalog.json"

    assert parse_catalog(missing_catalog) is None


def test_parse_catalog_returns_dict_keyed_by_unique_id() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert set(nodes) == {
        "model.fixture_project.stg_api_sports__fixtures",
        "model.fixture_project.int_fixtures_enriched_with_teams",
        "model.fixture_project.fixtures",
        "model.fixture_project.stg_bq__orders",
    }
    assert all(isinstance(node, CatalogNode) for node in nodes.values())


def test_parse_catalog_node_count_matches_fixture() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert len(nodes) == 4


def test_parse_catalog_node_name_is_correct() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert (
        nodes["model.fixture_project.stg_api_sports__fixtures"].name
        == "stg_api_sports__fixtures"
    )


def test_catalog_columns_are_extracted() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert nodes["model.fixture_project.fixtures"].columns == [
        CatalogColumn(
            name="fixture_id",
            data_type="INT64",
            comment="Warehouse identifier for a fixture.",
        ),
        CatalogColumn(name="fixture_date", data_type="TIMESTAMP", comment=""),
        CatalogColumn(
            name="is_finished",
            data_type="BOOLEAN",
            comment="Whether the fixture has completed.",
        ),
    ]


def test_catalog_column_name_is_lowercased() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert (
        nodes["model.fixture_project.stg_api_sports__fixtures"].columns[0].name
        == "fixture_id"
    )


def test_catalog_column_data_type_is_extracted() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert nodes["model.fixture_project.stg_bq__orders"].columns[2].data_type == "FLOAT64"


def test_catalog_column_comment_is_extracted_when_present() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert (
        nodes["model.fixture_project.int_fixtures_enriched_with_teams"].columns[2].comment
        == "Total points scored by both teams."
    )


def test_catalog_column_comment_is_empty_string_when_absent() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert nodes["model.fixture_project.stg_bq__orders"].columns[1].comment == ""


def test_only_model_nodes_are_included() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert "seed.fixture_project.country_codes" not in nodes
    assert "source.fixture_project.api_sports.fixtures" not in nodes


def test_extra_catalog_columns_not_in_manifest_are_included() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    column_names = {
        column.name
        for column in nodes["model.fixture_project.stg_api_sports__fixtures"].columns
    }
    assert "ingested_at" in column_names


def test_unknown_keys_in_catalog_json_do_not_raise(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "unexpected_top_level": True,
                "nodes": {
                    "model.fixture_project.example": {
                        "unique_id": "model.fixture_project.example",
                        "name": "example",
                        "unexpected_node_key": "ignored",
                        "columns": {
                            "id": {
                                "name": "id",
                                "type": "INT64",
                                "comment": "Identifier.",
                                "unexpected_column_key": "ignored",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    nodes = parse_catalog(catalog_path)

    assert nodes == {
        "model.fixture_project.example": CatalogNode(
            unique_id="model.fixture_project.example",
            name="example",
            columns=[
                CatalogColumn(
                    name="id",
                    data_type="INT64",
                    comment="Identifier.",
                )
            ],
        )
    }


def test_invalid_json_raises_value_error(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match=r"catalog\.json is not valid JSON:"):
        parse_catalog(catalog_path)


def test_null_comment_becomes_empty_string() -> None:
    nodes = parse_catalog(FIXTURE_CATALOG)

    assert nodes is not None
    assert nodes["model.fixture_project.stg_api_sports__fixtures"].columns[2].comment == ""


def test_absent_data_type_becomes_empty_string(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "nodes": {
                    "model.fixture_project.example": {
                        "unique_id": "model.fixture_project.example",
                        "name": "example",
                        "columns": {
                            "id": {
                                "name": "id",
                                "comment": "Identifier.",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    nodes = parse_catalog(catalog_path)

    assert nodes is not None
    assert nodes["model.fixture_project.example"].columns[0].data_type == ""
