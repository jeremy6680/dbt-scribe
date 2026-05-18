from __future__ import annotations

import json
from datetime import UTC, datetime

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.coverage_engine import (
    ColumnCoverage,
    CoverageResult,
    CoverageThresholds,
    LayerCoverage,
    ModelCoverage,
)
from dbt_scribe.catalog.reporters import json_reporter


def _model(
    name: str,
    *,
    layer: Layer = Layer.STAGING,
    described: bool = True,
    documented_columns: int = 2,
    tested_columns: int = 2,
    total_columns: int = 2,
) -> ModelCoverage:
    return ModelCoverage(
        name=name,
        unique_id=f"model.fixture.{name}",
        layer=layer,
        has_model_description=described,
        columns=[
            ColumnCoverage(
                name=f"column_{index}",
                has_description=index < documented_columns,
                test_count=1 if index < tested_columns else 0,
            )
            for index in range(total_columns)
        ],
    )


def _result(
    *,
    min_doc_coverage: float = 80.0,
    min_test_coverage: float = 70.0,
) -> CoverageResult:
    return CoverageResult(
        generated_at=datetime(2026, 5, 18, 12, 34, 56, tzinfo=UTC),
        project_name="fixture_project",
        adapter="bigquery",
        dbt_scribe_version="0.0.0-test",
        thresholds=CoverageThresholds(
            min_doc_coverage=min_doc_coverage,
            min_test_coverage=min_test_coverage,
        ),
        layers=[
            LayerCoverage(
                layer=Layer.STAGING,
                models=[
                    _model("stg_orders", layer=Layer.STAGING),
                    _model(
                        "stg_customers",
                        layer=Layer.STAGING,
                        described=False,
                        documented_columns=1,
                        tested_columns=0,
                    ),
                ],
            ),
            LayerCoverage(
                layer=Layer.MARTS,
                models=[_model("fct_orders", layer=Layer.MARTS)],
            ),
        ],
    )


def _payload(result: CoverageResult | None = None) -> dict:
    return json.loads(json_reporter.render(result or _result()))


def test_render_returns_valid_json() -> None:
    payload = _payload()

    assert payload["project"] == "fixture_project"


def test_required_top_level_keys_are_present() -> None:
    payload = _payload()

    assert set(payload) >= {
        "generated_at",
        "project",
        "adapter",
        "thresholds",
        "global",
        "layers",
        "models",
    }
    assert "project_name" not in payload
    assert "scores" not in payload
    assert "global_doc_score" not in payload
    assert "global_test_score" not in payload
    assert "passed" not in payload


def test_generated_at_is_iso_8601_utc_z() -> None:
    payload = _payload()

    parsed = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))

    assert payload["generated_at"] == "2026-05-18T12:34:56Z"
    assert parsed == datetime(2026, 5, 18, 12, 34, 56, tzinfo=UTC)


def test_models_array_contains_one_entry_per_model() -> None:
    result = _result()
    payload = _payload(result)

    assert len(payload["models"]) == result.model_count
    assert {model["name"] for model in payload["models"]} == {
        model.name for model in result.all_models
    }


def test_missing_column_lists_are_strings() -> None:
    payload = _payload()
    model = next(model for model in payload["models"] if model["name"] == "stg_customers")

    assert model["undocumented_columns"] == ["column_1"]
    assert model["untested_columns"] == ["column_0", "column_1"]
    assert all(isinstance(column, str) for column in model["undocumented_columns"])
    assert all(isinstance(column, str) for column in model["untested_columns"])


def test_passed_reflects_threshold_check() -> None:
    passing_payload = _payload(_result(min_doc_coverage=80, min_test_coverage=60))
    failing_payload = _payload(_result(min_doc_coverage=100, min_test_coverage=100))

    assert passing_payload["global"]["passed"] is True
    assert failing_payload["global"]["passed"] is False


def test_layers_are_keyed_by_layer_name() -> None:
    payload = _payload()

    assert set(payload["layers"]) == {"staging", "marts"}
    assert payload["layers"]["staging"] == {
        "model_count": 2,
        "doc_coverage": 75.0,
        "test_coverage": 50.0,
    }


def test_model_payload_matches_cdc_schema() -> None:
    payload = _payload()
    model = next(model for model in payload["models"] if model["name"] == "stg_customers")

    assert set(model) == {
        "name",
        "layer",
        "has_model_description",
        "column_count",
        "documented_columns",
        "tested_columns",
        "doc_coverage",
        "test_coverage",
        "undocumented_columns",
        "untested_columns",
    }
