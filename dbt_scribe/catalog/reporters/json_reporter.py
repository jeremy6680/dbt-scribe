from __future__ import annotations

import json
from typing import Any

from dbt_scribe.catalog.coverage_engine import CoverageResult, LayerCoverage, ModelCoverage


def render(result: CoverageResult) -> str:
    """Render coverage results as machine-readable JSON.

    Args:
        result: The computed CoverageResult from coverage_engine.

    Returns:
        A pretty-printed JSON string suitable for stdout, CI logs, or files.
    """
    return json.dumps(_result_payload(result), indent=2, sort_keys=True) + "\n"


def _result_payload(result: CoverageResult) -> dict[str, Any]:
    return {
        "generated_at": _isoformat_z(result.generated_at),
        "project": result.project_name,
        "adapter": result.adapter,
        "thresholds": {
            "min_doc_coverage": result.thresholds.min_doc_coverage,
            "min_test_coverage": result.thresholds.min_test_coverage,
        },
        "global": {
            "doc_coverage": result.global_doc_score,
            "test_coverage": result.global_test_score,
            "passed": result.passed,
        },
        "layers": {
            layer.layer.value: _layer_payload(layer)
            for layer in result.layers
        },
        "models": [_model_payload(model) for model in result.all_models],
    }


def _layer_payload(layer: LayerCoverage) -> dict[str, Any]:
    return {
        "model_count": layer.model_count,
        "doc_coverage": layer.column_doc_pct,
        "test_coverage": layer.test_pct,
    }


def _model_payload(model: ModelCoverage) -> dict[str, Any]:
    documented_columns = sum(1 for column in model.columns if column.has_description)
    tested_columns = sum(1 for column in model.columns if column.test_count > 0)
    return {
        "name": model.name,
        "layer": model.layer.value,
        "has_model_description": model.has_model_description,
        "column_count": model.column_count,
        "documented_columns": documented_columns,
        "tested_columns": tested_columns,
        "doc_coverage": model.column_doc_coverage,
        "test_coverage": model.test_coverage,
        "undocumented_columns": model.undocumented_columns,
        "untested_columns": model.untested_columns,
    }


def _isoformat_z(value) -> str:
    formatted = value.isoformat()
    if formatted.endswith("+00:00"):
        return f"{formatted[:-6]}Z"
    return formatted
