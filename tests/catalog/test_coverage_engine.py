from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.catalog_parser import CatalogColumn, CatalogNode, parse_catalog
from dbt_scribe.catalog.coverage_engine import compute_coverage
from dbt_scribe.config import (
    CacheConfig,
    ConventionsConfig,
    CoverageConfig,
    DocsConfig,
    ScribeConfig,
    TestsConfig,
)
from dbt_scribe.parsers.manifest_parser import ManifestColumn, ManifestNode
from dbt_scribe.parsers.yaml_parser import YamlColumn, YamlModel

FIXTURE_PROJECT = Path(__file__).parent.parent / "fixtures" / "dbt_project"
FIXTURE_CATALOG = FIXTURE_PROJECT / "target" / "catalog.json"


def _config(
    *,
    min_doc_coverage: int = 80,
    min_test_coverage: int = 70,
) -> ScribeConfig:
    return ScribeConfig.model_construct(
        version=1,
        llm=None,
        docs=DocsConfig(),
        tests=TestsConfig(),
        coverage=CoverageConfig(
            min_doc_coverage=min_doc_coverage,
            min_test_coverage=min_test_coverage,
        ),
        conventions=ConventionsConfig(),
        cache=CacheConfig(),
        model_root="models",
    )


def _node(
    name: str,
    columns: list[str],
    *,
    layer: str = "staging",
    unique_id: str | None = None,
    adapter_type: str | None = "bigquery",
) -> ManifestNode:
    return ManifestNode(
        unique_id=unique_id or f"model.fixture_project.{name}",
        name=name,
        fqn=["fixture_project", layer, name],
        resource_type="model",
        compiled_code="select 1",
        columns={
            column_name: ManifestColumn(
                name=column_name,
                data_type=None,
                description=None,
            )
            for column_name in columns
        },
        depends_on_nodes=[],
        tags=[],
        materialized="view",
        path=f"models/{layer}/{name}.sql",
        adapter_type=adapter_type,
        config={},
    )


def _yaml_model(
    name: str,
    columns: dict[str, tuple[str | None, list[Any]]],
    *,
    description: str | None = "Model description.",
) -> YamlModel:
    return YamlModel(
        name=name,
        description=description,
        columns={
            column_name: YamlColumn(
                name=column_name,
                description=column_description,
                tests=tests,
            )
            for column_name, (column_description, tests) in columns.items()
        },
    )


def test_all_models_fully_documented_and_tested_scores_100() -> None:
    nodes = [_node("stg_orders", ["order_id"]), _node("stg_customers", ["customer_id"])]
    yaml_models = {
        "stg_orders": _yaml_model("stg_orders", {"order_id": ("Order id.", ["unique"])}),
        "stg_customers": _yaml_model(
            "stg_customers",
            {"customer_id": ("Customer id.", ["not_null"])},
        ),
    }

    result = compute_coverage(nodes, None, yaml_models, _config())

    assert result.global_doc_score == pytest.approx(100.0)
    assert result.global_test_score == pytest.approx(100.0)


def test_model_with_no_yaml_counts_columns_as_undocumented_and_untested() -> None:
    result = compute_coverage([_node("stg_orders", ["order_id", "amount"])], None, {}, _config())

    model = result.all_models[0]
    assert model.has_model_description is False
    assert model.undocumented_columns == ["order_id", "amount"]
    assert model.untested_columns == ["order_id", "amount"]
    assert [column.test_count for column in model.columns] == [0, 0]


def test_catalog_columns_supplement_manifest_columns_with_union_count() -> None:
    catalog = parse_catalog(FIXTURE_CATALOG)
    assert catalog is not None
    node = _node(
        "stg_api_sports__fixtures",
        ["fixture_id", "league_id"],
        unique_id="model.fixture_project.stg_api_sports__fixtures",
    )

    result = compute_coverage([node], catalog, {}, _config())

    assert result.all_models[0].column_count == 4
    assert [column.name for column in result.all_models[0].columns] == [
        "fixture_id",
        "league_id",
        "fixture_status",
        "ingested_at",
    ]


def test_catalog_absent_uses_manifest_columns_only() -> None:
    node = _node("stg_api_sports__fixtures", ["fixture_id", "league_id"])

    result = compute_coverage([node], None, {}, _config())

    assert result.all_models[0].column_count == 2
    assert [column.name for column in result.all_models[0].columns] == [
        "fixture_id",
        "league_id",
    ]


def test_doc_reference_in_column_description_counts_as_documented() -> None:
    node = _node("stg_orders", ["order_id"])
    yaml_models = {
        "stg_orders": _yaml_model(
            "stg_orders",
            {"order_id": ('{{ doc("order_id") }}', [])},
        )
    }

    result = compute_coverage([node], None, yaml_models, _config())

    assert result.all_models[0].columns[0].has_description is True


def test_model_with_zero_columns_has_zero_scores_without_division_error() -> None:
    node = _node("stg_empty", [])

    result = compute_coverage([node], None, {"stg_empty": _yaml_model("stg_empty", {})}, _config())

    assert result.all_models[0].column_doc_coverage == pytest.approx(0.0)
    assert result.all_models[0].test_coverage == pytest.approx(0.0)
    assert result.global_doc_score == pytest.approx(0.0)
    assert result.global_test_score == pytest.approx(0.0)


def test_global_doc_score_is_weighted_by_column_count() -> None:
    nodes = [
        _node("stg_wide", ["c1", "c2", "c3", "c4"]),
        _node("stg_narrow", ["id"]),
    ]
    yaml_models = {
        "stg_wide": _yaml_model(
            "stg_wide",
            {
                "c1": ("c1.", []),
                "c2": ("c2.", []),
                "c3": (None, []),
                "c4": (None, []),
            },
        ),
        "stg_narrow": _yaml_model("stg_narrow", {"id": ("id.", [])}),
    }

    result = compute_coverage(nodes, None, yaml_models, _config())

    assert result.global_doc_score == pytest.approx(60.0)


def test_per_layer_column_doc_and_test_percentages_are_correct_for_fixture_shape() -> None:
    nodes = [
        _node("stg_orders", ["order_id", "amount"], layer="staging"),
        _node("int_orders", ["order_id", "amount"], layer="intermediate"),
    ]
    yaml_models = {
        "stg_orders": _yaml_model(
            "stg_orders",
            {
                "order_id": ("Order id.", ["unique"]),
                "amount": (None, []),
            },
        ),
        "int_orders": _yaml_model(
            "int_orders",
            {
                "order_id": ("Order id.", ["not_null"]),
                "amount": ("Amount.", ["not_null"]),
            },
        ),
    }

    result = compute_coverage(nodes, None, yaml_models, _config())
    by_layer = {layer.layer: layer for layer in result.layers}

    assert by_layer[Layer.STAGING].column_doc_pct == pytest.approx(50.0)
    assert by_layer[Layer.STAGING].test_pct == pytest.approx(50.0)
    assert by_layer[Layer.INTERMEDIATE].column_doc_pct == pytest.approx(100.0)
    assert by_layer[Layer.INTERMEDIATE].test_pct == pytest.approx(100.0)


def test_passed_reflects_doc_and_test_thresholds() -> None:
    node = _node("stg_orders", ["order_id"])
    yaml_models = {
        "stg_orders": _yaml_model("stg_orders", {"order_id": ("Order id.", ["unique"])})
    }

    passing = compute_coverage(
        [node],
        None,
        yaml_models,
        _config(min_doc_coverage=100, min_test_coverage=100),
    )
    failing = compute_coverage(
        [node],
        None,
        yaml_models,
        _config(min_doc_coverage=100, min_test_coverage=101),
    )

    assert passing.passed is True
    assert failing.passed is False


def test_layer_model_doc_pct_counts_models_with_descriptions() -> None:
    nodes = [_node("stg_orders", ["order_id"]), _node("stg_customers", ["customer_id"])]
    yaml_models = {
        "stg_orders": _yaml_model(
            "stg_orders",
            {"order_id": ("Order id.", [])},
            description="Orders.",
        ),
        "stg_customers": _yaml_model(
            "stg_customers",
            {"customer_id": ("Customer id.", [])},
            description=None,
        ),
    }

    result = compute_coverage(nodes, None, yaml_models, _config())

    assert result.layers[0].model_doc_pct == pytest.approx(50.0)


def test_empty_nodes_returns_empty_result_with_zero_scores() -> None:
    result = compute_coverage([], None, {}, _config())

    assert result.layers == []
    assert result.all_models == []
    assert result.model_count == 0
    assert result.global_doc_score == pytest.approx(0.0)
    assert result.global_test_score == pytest.approx(0.0)
    assert result.adapter == "unknown"


def test_catalog_columns_are_merged_case_insensitively() -> None:
    node = _node("stg_orders", ["Order_ID"])
    catalog = {
        node.unique_id: CatalogNode(
            unique_id=node.unique_id,
            name=node.name,
            columns=[
                CatalogColumn(name="order_id", data_type="INT64", comment=""),
                CatalogColumn(name="amount", data_type="FLOAT64", comment=""),
            ],
        )
    }

    result = compute_coverage([node], catalog, {}, _config())

    assert [column.name for column in result.all_models[0].columns] == [
        "Order_ID",
        "amount",
    ]
