from __future__ import annotations

import io
from datetime import UTC, datetime

from rich.console import Console

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.coverage_engine import (
    ColumnCoverage,
    CoverageResult,
    CoverageThresholds,
    LayerCoverage,
    ModelCoverage,
)
from dbt_scribe.catalog.reporters import terminal_reporter


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
    layers: list[LayerCoverage] | None = None,
    min_doc_coverage: float = 80.0,
    min_test_coverage: float = 70.0,
) -> CoverageResult:
    return CoverageResult(
        generated_at=datetime(2026, 5, 17, tzinfo=UTC),
        project_name="fixture_project",
        adapter="bigquery",
        dbt_scribe_version="0.0.0-test",
        thresholds=CoverageThresholds(
            min_doc_coverage=min_doc_coverage,
            min_test_coverage=min_test_coverage,
        ),
        layers=layers
        if layers is not None
        else [
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
                layer=Layer.INTERMEDIATE,
                models=[_model("int_orders", layer=Layer.INTERMEDIATE)],
            ),
            LayerCoverage(
                layer=Layer.MARTS,
                models=[_model("fct_orders", layer=Layer.MARTS)],
            ),
        ],
    )


def _render(result: CoverageResult, layer_filter: str | None = None) -> str:
    output = io.StringIO()
    console = Console(
        file=output,
        force_terminal=True,
        color_system="standard",
        no_color=False,
        highlight=False,
        width=120,
        legacy_windows=False,
    )
    terminal_reporter.Console = lambda: console  # type: ignore[method-assign]

    terminal_reporter.render(result, layer_filter=layer_filter)

    return output.getvalue()


def test_render_contains_project_name() -> None:
    output = _render(_result())

    assert "fixture_project" in output


def test_render_contains_model_names() -> None:
    result = _result()
    output = _render(result)

    for model in result.all_models:
        assert model.name in output


def test_layer_filter_respected() -> None:
    output = _render(_result(), layer_filter="staging")

    assert "STAGING" in output
    assert "INTERMEDIATE" not in output
    assert "MARTS" not in output


def test_layer_filter_unknown() -> None:
    output = _render(_result(), layer_filter="unknown-layer")

    assert "STAGING" not in output
    assert "INTERMEDIATE" not in output
    assert "MARTS" not in output


def test_color_threshold_green() -> None:
    output = _render(
        _result(
            layers=[
                LayerCoverage(
                    layer=Layer.STAGING,
                    models=[
                        _model(
                            "stg_orders", documented_columns=5, tested_columns=5, total_columns=5
                        )
                    ],
                )
            ],
            min_doc_coverage=80,
            min_test_coverage=70,
        )
    )

    assert "\x1b[32m" in output
    assert "PASS" in output


def test_color_threshold_amber() -> None:
    output = _render(
        _result(
            layers=[
                LayerCoverage(
                    layer=Layer.STAGING,
                    models=[
                        _model(
                            "stg_orders", documented_columns=7, tested_columns=7, total_columns=10
                        )
                    ],
                )
            ],
            min_doc_coverage=80,
            min_test_coverage=80,
        )
    )

    assert "\x1b[33m" in output
    assert "WARN" in output


def test_color_threshold_red() -> None:
    output = _render(
        _result(
            layers=[
                LayerCoverage(
                    layer=Layer.STAGING,
                    models=[
                        _model(
                            "stg_orders", documented_columns=5, tested_columns=5, total_columns=10
                        )
                    ],
                )
            ],
            min_doc_coverage=80,
            min_test_coverage=80,
        )
    )

    assert "\x1b[31m" in output
    assert "FAIL" in output


def test_zero_model_layer() -> None:
    output = _render(_result(layers=[LayerCoverage(layer=Layer.MARTS, models=[])]))

    assert "No models in this layer." in output


def test_compact_mode_activates() -> None:
    models = [
        _model(f"stg_model_{index}", documented_columns=1, tested_columns=1, total_columns=2)
        for index in range(21)
    ]

    output = _render(_result(layers=[LayerCoverage(layer=Layer.STAGING, models=models)]))

    assert "Compact mode: > 20 models" in output
    assert "1/2" not in output
    assert "50%" in output


def test_compact_mode_inactive() -> None:
    output = _render(
        _result(
            layers=[
                LayerCoverage(
                    layer=Layer.STAGING,
                    models=[
                        _model(
                            "stg_orders", documented_columns=1, tested_columns=1, total_columns=2
                        )
                    ],
                )
            ]
        )
    )

    assert "Compact mode: > 20 models" not in output
    assert "1/2" in output
