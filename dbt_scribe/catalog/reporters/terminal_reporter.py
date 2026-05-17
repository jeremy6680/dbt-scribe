from __future__ import annotations

from collections.abc import Iterable

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.coverage_engine import (
    CoverageResult,
    CoverageThresholds,
    LayerCoverage,
    ModelCoverage,
)

_LAYER_ORDER = (Layer.STAGING, Layer.INTERMEDIATE, Layer.MARTS)


def render(result: CoverageResult, layer_filter: str | None = None) -> None:
    """Render coverage results to the terminal using Rich.

    Args:
        result: The computed CoverageResult from coverage_engine.
        layer_filter: If set, only render the matching layer ("staging",
            "intermediate", or "marts"). None = render all layers.
    """
    console = Console()
    compact = result.model_count > 20

    _render_header(console, result)
    for layer in _filtered_layers(result.layers, layer_filter):
        _render_layer(console, layer, result.thresholds, compact)

    _render_summary(console, result)
    if compact:
        console.print("Compact mode: > 20 models", style="dim")


def _render_header(console: Console, result: CoverageResult) -> None:
    body = "\n".join(
        [
            f"Project: {result.project_name}",
            f"Models: {result.model_count}",
            f"Adapter: {result.adapter}",
        ]
    )
    console.print(Panel(body, title="dbt-scribe catalog", border_style="cyan"))


def _filtered_layers(
    layers: Iterable[LayerCoverage],
    layer_filter: str | None,
) -> list[LayerCoverage]:
    by_layer = {layer.layer: layer for layer in layers}
    if layer_filter is not None:
        requested_layer = _layer_from_filter(layer_filter)
        return [by_layer[requested_layer]] if requested_layer in by_layer else []

    ordered_layers = [by_layer[layer] for layer in _LAYER_ORDER if layer in by_layer]
    extra_layers = [
        layer
        for layer in layers
        if layer.layer not in _LAYER_ORDER
        and layer.layer not in {item.layer for item in ordered_layers}
    ]
    return ordered_layers + extra_layers


def _layer_from_filter(layer_filter: str) -> Layer:
    try:
        layer = Layer(layer_filter.lower())
    except ValueError:
        return Layer.UNKNOWN
    return layer if layer in _LAYER_ORDER else Layer.UNKNOWN


def _render_layer(
    console: Console,
    layer: LayerCoverage,
    thresholds: CoverageThresholds,
    compact: bool,
) -> None:
    console.print()
    console.print(f"{layer.layer.value.upper()} ({layer.model_count} models)", style="bold")

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Model", overflow="fold")
    table.add_column("Desc", justify="center")
    table.add_column("Col docs", justify="right")
    table.add_column("Tests", justify="right")
    table.add_column("Score", justify="right")

    if not layer.models:
        table.add_row("No models in this layer.", "", "", "", "")
        console.print(table)
        return

    for model in layer.models:
        table.add_row(
            model.name,
            "PASS ✅" if model.has_model_description else "FAIL ❌",
            _coverage_cell(
                model.column_doc_coverage, _documented_columns(model), model.column_count, compact
            ),
            _coverage_cell(
                model.test_coverage, _tested_columns(model), model.column_count, compact
            ),
            _score_text(_model_score(model), _combined_threshold(thresholds)),
        )

    table.add_row(
        Text("Layer score:", style="bold"),
        "",
        _score_text(layer.column_doc_pct, thresholds.min_doc_coverage),
        _score_text(layer.test_pct, thresholds.min_test_coverage),
        _score_text(
            f"doc {_format_pct(layer.column_doc_pct)} · test {_format_pct(layer.test_pct)}",
            _combined_threshold(thresholds),
            score=_model_score_for_layer(layer),
        ),
        end_section=True,
    )
    console.print(table)


def _render_summary(console: Console, result: CoverageResult) -> None:
    console.print()
    table = Table(title="Global Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Metric")
    table.add_column("Score", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Status")

    table.add_row(
        "Documentation",
        _score_text(result.global_doc_score, result.thresholds.min_doc_coverage),
        _format_pct(result.thresholds.min_doc_coverage),
        _status_text(result.global_doc_score, result.thresholds.min_doc_coverage),
    )
    table.add_row(
        "Tests",
        _score_text(result.global_test_score, result.thresholds.min_test_coverage),
        _format_pct(result.thresholds.min_test_coverage),
        _status_text(result.global_test_score, result.thresholds.min_test_coverage),
    )
    console.print(table)


def _coverage_cell(score: float, numerator: int, denominator: int, compact: bool) -> str:
    if compact:
        return _format_pct(score)
    return f"{numerator}/{denominator}"


def _score_text(label: str | float, threshold: float, *, score: float | None = None) -> Text:
    actual_score = label if isinstance(label, float) else score
    if actual_score is None:
        raise ValueError("score is required when label is not numeric")
    text = _format_pct(label) if isinstance(label, float) else label
    return Text(text, style=_score_style(actual_score, threshold))


def _status_text(score: float, threshold: float) -> Text:
    if score >= threshold:
        return Text("PASS ✅", style="green")
    if threshold - score <= 20:
        return Text("WARN ⚠", style="yellow")
    return Text("FAIL ❌", style="red")


def _score_style(score: float, threshold: float) -> str:
    if score >= threshold:
        return "green"
    if threshold - score <= 20:
        return "yellow"
    return "red"


def _model_score(model: ModelCoverage) -> float:
    return (model.column_doc_coverage + model.test_coverage) / 2


def _model_score_for_layer(layer: LayerCoverage) -> float:
    return (layer.column_doc_pct + layer.test_pct) / 2


def _combined_threshold(thresholds: CoverageThresholds) -> float:
    return (thresholds.min_doc_coverage + thresholds.min_test_coverage) / 2


def _documented_columns(model: ModelCoverage) -> int:
    return sum(1 for column in model.columns if column.has_description)


def _tested_columns(model: ModelCoverage) -> int:
    return sum(1 for column in model.columns if column.test_count > 0)


def _format_pct(value: float) -> str:
    return f"{value:.0f}%"
