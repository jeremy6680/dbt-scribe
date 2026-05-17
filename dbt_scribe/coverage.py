from __future__ import annotations

from dbt_scribe.catalog.coverage_engine import CoverageResult
from dbt_scribe.catalog.reporters import terminal_reporter


def print_coverage_report(
    result: CoverageResult,
    layer_filter: str | None = None,
) -> None:
    """Print a documentation and test coverage report.

    Args:
        result: The computed CoverageResult from coverage_engine.
        layer_filter: If set, only render the matching layer. None renders all layers.
    """
    terminal_reporter.render(result, layer_filter=layer_filter)
