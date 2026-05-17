from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dbt_scribe.analyzer import Layer
from dbt_scribe.catalog.coverage_engine import (
    ColumnCoverage,
    CoverageResult,
    CoverageThresholds,
    LayerCoverage,
    ModelCoverage,
)
from dbt_scribe.catalog.reporters import html_reporter


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


def _result() -> CoverageResult:
    return CoverageResult(
        generated_at=datetime(2026, 5, 17, tzinfo=UTC),
        project_name="fixture_project",
        adapter="bigquery",
        dbt_scribe_version="0.0.0-test",
        thresholds=CoverageThresholds(min_doc_coverage=80, min_test_coverage=70),
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
                layer=Layer.INTERMEDIATE,
                models=[_model("int_orders", layer=Layer.INTERMEDIATE)],
            ),
            LayerCoverage(
                layer=Layer.MARTS,
                models=[_model("fct_orders", layer=Layer.MARTS)],
            ),
        ],
    )


def test_render_creates_file_at_specified_path(tmp_path: Path) -> None:
    output_path = tmp_path / "catalog-report.html"

    html_reporter.render(_result(), output_path)

    assert output_path.exists()


def test_render_creates_parent_directory(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "reports" / "catalog-report.html"

    html_reporter.render(_result(), output_path)

    assert output_path.exists()


def test_render_contains_project_model_names_and_global_scores(tmp_path: Path) -> None:
    result = _result()
    output_path = tmp_path / "catalog-report.html"

    html_reporter.render(result, output_path)
    html = output_path.read_text(encoding="utf-8")

    assert "fixture_project" in html
    assert "100%" in html
    assert "75%" in html
    for model in result.all_models:
        assert model.name in html


def test_render_is_self_contained_without_external_assets(tmp_path: Path) -> None:
    output_path = tmp_path / "catalog-report.html"

    html_reporter.render(_result(), output_path)
    html = output_path.read_text(encoding="utf-8")

    assert "<link" not in html
    assert "script src=" not in html
    assert "<img" not in html
    assert "http://cdn" not in html
    assert "https://cdn" not in html


def test_render_contains_semantic_table_and_details(tmp_path: Path) -> None:
    output_path = tmp_path / "catalog-report.html"

    html_reporter.render(_result(), output_path)
    html = output_path.read_text(encoding="utf-8")

    assert "<main" in html
    assert "<section" in html
    assert "<caption>" in html
    assert 'scope="col"' in html
    assert 'scope="row"' in html
    assert "<details>" in html
