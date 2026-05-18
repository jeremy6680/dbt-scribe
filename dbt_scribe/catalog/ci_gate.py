from __future__ import annotations

from dbt_scribe.catalog.coverage_engine import CoverageResult


def check(result: CoverageResult, ci_mode: bool) -> int:
    """Return the process exit code implied by the coverage result.

    Args:
        result: The computed CoverageResult from coverage_engine.
        ci_mode: Whether threshold failures should fail the caller.

    Returns:
        0 when CI mode is disabled or thresholds pass, otherwise 1.
    """
    if not ci_mode:
        return 0
    return 0 if result.passed else 1


def format_failure_message(result: CoverageResult) -> str:
    """Return a human-readable summary of failed coverage thresholds."""
    failures: list[str] = []

    if result.global_doc_score < result.thresholds.min_doc_coverage:
        failures.append(
            _format_metric_failure(
                "Documentation coverage",
                result.global_doc_score,
                result.thresholds.min_doc_coverage,
            )
        )

    if result.global_test_score < result.thresholds.min_test_coverage:
        failures.append(
            _format_metric_failure(
                "Test coverage",
                result.global_test_score,
                result.thresholds.min_test_coverage,
            )
        )

    if not failures:
        return "Coverage thresholds passed."

    return "Coverage thresholds failed:\n" + "\n".join(f"- {failure}" for failure in failures)


def _format_metric_failure(label: str, actual: float, threshold: float) -> str:
    shortfall = threshold - actual
    return (
        f"{label} is {_format_pct(actual)}; threshold is {_format_pct(threshold)} "
        f"({_format_pct(shortfall)} below)."
    )


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"
