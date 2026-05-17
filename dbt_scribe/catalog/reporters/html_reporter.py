from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from dbt_scribe.catalog.coverage_engine import CoverageResult, ModelCoverage

_TEMPLATE_NAME = "catalog_report.html.j2"
_COMMAND = "dbt-scribe catalog --output html"


def render(result: CoverageResult, output_path: Path) -> None:
    """Render coverage results to a self-contained HTML report.

    Args:
        result: The computed CoverageResult from coverage_engine.
        output_path: Destination file path for the generated HTML report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    environment = Environment(
        loader=PackageLoader("dbt_scribe", "templates"),
        autoescape=select_autoescape(("html", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(_TEMPLATE_NAME)

    output_path.write_text(
        template.render(
            command=_COMMAND,
            result=result,
            layers=result.layers,
            models=[_model_view(model, result) for model in result.all_models],
            global_doc=_metric_view(
                label="Documentation coverage",
                score=result.global_doc_score,
                threshold=result.thresholds.min_doc_coverage,
            ),
            global_test=_metric_view(
                label="Test coverage",
                score=result.global_test_score,
                threshold=result.thresholds.min_test_coverage,
            ),
            threshold_status="PASS" if result.passed else "FAIL",
        ),
        encoding="utf-8",
    )


def _model_view(model: ModelCoverage, result: CoverageResult) -> dict[str, Any]:
    documented_columns = sum(1 for column in model.columns if column.has_description)
    tested_columns = sum(1 for column in model.columns if column.test_count > 0)
    return {
        "name": model.name,
        "layer": model.layer.value,
        "has_description": model.has_model_description,
        "column_count": model.column_count,
        "documented_columns": documented_columns,
        "tested_columns": tested_columns,
        "undocumented_columns": model.undocumented_columns,
        "untested_columns": model.untested_columns,
        "doc_metric": _metric_view(
            label="Column documentation",
            score=model.column_doc_coverage,
            threshold=result.thresholds.min_doc_coverage,
            numerator=documented_columns,
            denominator=model.column_count,
        ),
        "test_metric": _metric_view(
            label="Column tests",
            score=model.test_coverage,
            threshold=result.thresholds.min_test_coverage,
            numerator=tested_columns,
            denominator=model.column_count,
        ),
    }


def _metric_view(
    *,
    label: str,
    score: float,
    threshold: float,
    numerator: int | None = None,
    denominator: int | None = None,
) -> dict[str, Any]:
    if denominator == 0:
        return {
            "label": label,
            "score": score,
            "score_text": "N/A",
            "threshold": threshold,
            "threshold_text": _format_pct(threshold),
            "count_text": "N/A",
            "status": "N/A",
            "status_label": "N/A",
            "status_icon": "N/A",
            "status_class": "na",
            "progress": 0,
        }

    status_class = _status_class(score, threshold)
    return {
        "label": label,
        "score": score,
        "score_text": _format_pct(score),
        "threshold": threshold,
        "threshold_text": _format_pct(threshold),
        "count_text": (
            f"{numerator}/{denominator}"
            if numerator is not None and denominator is not None
            else _format_pct(score)
        ),
        "status": _status_label(status_class),
        "status_label": _status_label(status_class),
        "status_icon": _status_icon(status_class),
        "status_class": status_class,
        "progress": max(0, min(100, round(score))),
    }


def _status_class(score: float, threshold: float) -> str:
    if score >= threshold:
        return "pass"
    if threshold - score <= 20:
        return "warn"
    return "fail"


def _status_label(status_class: str) -> str:
    return {
        "pass": "PASS",
        "warn": "WARN",
        "fail": "FAIL",
        "na": "N/A",
    }[status_class]


def _status_icon(status_class: str) -> str:
    return {
        "pass": "OK",
        "warn": "WARN",
        "fail": "FAIL",
        "na": "N/A",
    }[status_class]


def _format_pct(value: float) -> str:
    return f"{value:.0f}%"
