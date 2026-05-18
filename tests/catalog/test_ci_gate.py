from __future__ import annotations

from datetime import UTC, datetime

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.ci_gate import check, format_failure_message
from dbt_scribe.catalog.coverage_engine import (
    ColumnCoverage,
    CoverageResult,
    CoverageThresholds,
    LayerCoverage,
    ModelCoverage,
)


def _model(
    name: str,
    *,
    documented_columns: int,
    tested_columns: int,
    total_columns: int = 10,
) -> ModelCoverage:
    return ModelCoverage(
        name=name,
        unique_id=f"model.fixture.{name}",
        layer=Layer.STAGING,
        has_model_description=True,
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
    documented_columns: int = 10,
    tested_columns: int = 10,
    min_doc_coverage: float = 80.0,
    min_test_coverage: float = 70.0,
) -> CoverageResult:
    return CoverageResult(
        generated_at=datetime(2026, 5, 18, tzinfo=UTC),
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
                    _model(
                        "stg_orders",
                        documented_columns=documented_columns,
                        tested_columns=tested_columns,
                    )
                ],
            )
        ],
    )


def test_ci_mode_false_always_returns_zero_even_when_thresholds_fail() -> None:
    result = _result(documented_columns=0, tested_columns=0)

    assert check(result, ci_mode=False) == 0


def test_ci_mode_true_returns_zero_when_thresholds_pass() -> None:
    result = _result(documented_columns=8, tested_columns=7)

    assert check(result, ci_mode=True) == 0


def test_ci_mode_true_returns_one_when_doc_score_below_threshold() -> None:
    result = _result(documented_columns=7, tested_columns=10)

    assert check(result, ci_mode=True) == 1


def test_ci_mode_true_returns_one_when_test_score_below_threshold() -> None:
    result = _result(documented_columns=10, tested_columns=6)

    assert check(result, ci_mode=True) == 1


def test_ci_mode_true_returns_one_when_both_scores_below_thresholds() -> None:
    result = _result(documented_columns=7, tested_columns=6)

    assert check(result, ci_mode=True) == 1


def test_failure_message_contains_doc_threshold_values_and_actual_score() -> None:
    result = _result(documented_columns=7, tested_columns=10)

    message = format_failure_message(result)

    assert "Coverage thresholds failed:" in message
    assert "Documentation coverage" in message
    assert "70.0%" in message
    assert "80.0%" in message
    assert "10.0% below" in message
    assert "Test coverage" not in message


def test_failure_message_contains_test_threshold_values_and_actual_score() -> None:
    result = _result(documented_columns=10, tested_columns=6)

    message = format_failure_message(result)

    assert "Test coverage" in message
    assert "60.0%" in message
    assert "70.0%" in message
    assert "10.0% below" in message
    assert "Documentation coverage" not in message


def test_failure_message_contains_both_failures_when_both_scores_fail() -> None:
    result = _result(documented_columns=7, tested_columns=6)

    message = format_failure_message(result)

    assert "Documentation coverage" in message
    assert "Test coverage" in message


def test_failure_message_reports_pass_when_thresholds_pass() -> None:
    result = _result(documented_columns=10, tested_columns=10)

    assert format_failure_message(result) == "Coverage thresholds passed."
