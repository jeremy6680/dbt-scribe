from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dbt_scribe import __version__
from dbt_scribe.analyzer import Layer, detect_layer
from dbt_scribe.catalog.catalog_parser import CatalogNode
from dbt_scribe.config import ScribeConfig
from dbt_scribe.parsers.manifest_parser import ManifestColumn, ManifestNode
from dbt_scribe.parsers.yaml_parser import YamlModel, is_description_set


@dataclass
class CoverageThresholds:
    """Minimum coverage percentages required for a successful report."""

    min_doc_coverage: float
    min_test_coverage: float


@dataclass
class ColumnCoverage:
    """Documentation and test coverage for a single model column."""

    name: str
    has_description: bool
    test_count: int


@dataclass
class ModelCoverage:
    """Documentation and test coverage for a single dbt model."""

    name: str
    unique_id: str
    layer: Layer
    has_model_description: bool
    columns: list[ColumnCoverage]

    @property
    def column_doc_coverage(self) -> float:
        """Return the percentage of columns with descriptions."""
        if not self.columns:
            return 0.0
        documented_count = sum(1 for column in self.columns if column.has_description)
        return documented_count / len(self.columns) * 100

    @property
    def test_coverage(self) -> float:
        """Return the percentage of columns with at least one test."""
        if not self.columns:
            return 0.0
        tested_count = sum(1 for column in self.columns if column.test_count > 0)
        return tested_count / len(self.columns) * 100

    @property
    def undocumented_columns(self) -> list[str]:
        """Return column names that do not have descriptions."""
        return [column.name for column in self.columns if not column.has_description]

    @property
    def untested_columns(self) -> list[str]:
        """Return column names that do not have tests."""
        return [column.name for column in self.columns if column.test_count == 0]

    @property
    def column_count(self) -> int:
        """Return the number of columns included in coverage."""
        return len(self.columns)


@dataclass
class LayerCoverage:
    """Aggregated coverage for a dbt project layer."""

    layer: Layer
    models: list[ModelCoverage]

    @property
    def model_doc_pct(self) -> float:
        """Return the percentage of models with descriptions."""
        if not self.models:
            return 0.0
        documented_count = sum(1 for model in self.models if model.has_model_description)
        return documented_count / len(self.models) * 100

    @property
    def column_doc_pct(self) -> float:
        """Return the percentage of columns with descriptions in this layer."""
        total_columns = sum(model.column_count for model in self.models)
        if total_columns == 0:
            return 0.0
        documented_columns = sum(
            1 for model in self.models for column in model.columns if column.has_description
        )
        return documented_columns / total_columns * 100

    @property
    def test_pct(self) -> float:
        """Return the percentage of columns with tests in this layer."""
        total_columns = sum(model.column_count for model in self.models)
        if total_columns == 0:
            return 0.0
        tested_columns = sum(
            1 for model in self.models for column in model.columns if column.test_count > 0
        )
        return tested_columns / total_columns * 100

    @property
    def model_count(self) -> int:
        """Return the number of models included in this layer."""
        return len(self.models)


@dataclass
class CoverageResult:
    """Project-level coverage report."""

    generated_at: datetime
    project_name: str
    adapter: str
    dbt_scribe_version: str
    thresholds: CoverageThresholds
    layers: list[LayerCoverage]

    @property
    def global_doc_score(self) -> float:
        """Return global documentation coverage weighted by model column count."""
        total_columns = sum(model.column_count for model in self.all_models)
        if total_columns == 0:
            return 0.0
        weighted_score = sum(
            model.column_doc_coverage * model.column_count for model in self.all_models
        )
        return weighted_score / total_columns

    @property
    def global_test_score(self) -> float:
        """Return global test coverage weighted by model column count."""
        total_columns = sum(model.column_count for model in self.all_models)
        if total_columns == 0:
            return 0.0
        weighted_score = sum(model.test_coverage * model.column_count for model in self.all_models)
        return weighted_score / total_columns

    @property
    def passed(self) -> bool:
        """Return whether global coverage scores meet configured thresholds."""
        return (
            self.global_doc_score >= self.thresholds.min_doc_coverage
            and self.global_test_score >= self.thresholds.min_test_coverage
        )

    @property
    def all_models(self) -> list[ModelCoverage]:
        """Return all model coverage entries across layers."""
        return [model for layer in self.layers for model in layer.models]

    @property
    def model_count(self) -> int:
        """Return the number of models included in the report."""
        return len(self.all_models)


def compute_coverage(
    nodes: list[ManifestNode],
    catalog: dict[str, CatalogNode] | None,
    yaml_models: dict[str, YamlModel | None],
    config: ScribeConfig,
) -> CoverageResult:
    """Compute documentation and test coverage from parsed dbt project metadata.

    Args:
        nodes: Manifest model nodes to include in the report.
        catalog: Optional catalog nodes keyed by unique id. When present,
            catalog columns supplement manifest columns.
        yaml_models: Existing YAML models keyed by model name.
        config: dbt-scribe configuration containing thresholds and conventions.

    Returns:
        A typed coverage result with model, layer, and global aggregates.
    """
    models_by_layer: dict[Layer, list[ModelCoverage]] = {}

    for node in nodes:
        layer = detect_layer(node.fqn, config.conventions)
        model_coverage = _compute_model_coverage(
            node=node,
            layer=layer,
            catalog_node=catalog.get(node.unique_id) if catalog is not None else None,
            yaml_model=yaml_models.get(node.name),
        )
        models_by_layer.setdefault(layer, []).append(model_coverage)

    return CoverageResult(
        generated_at=datetime.now(UTC),
        project_name=_project_name(config, nodes),
        adapter=_adapter(nodes),
        dbt_scribe_version=__version__,
        thresholds=CoverageThresholds(
            min_doc_coverage=float(config.coverage.min_doc_coverage),
            min_test_coverage=float(config.coverage.min_test_coverage),
        ),
        layers=[
            LayerCoverage(layer=layer, models=models)
            for layer, models in models_by_layer.items()
        ],
    )


def _compute_model_coverage(
    *,
    node: ManifestNode,
    layer: Layer,
    catalog_node: CatalogNode | None,
    yaml_model: YamlModel | None,
) -> ModelCoverage:
    columns = [
        _compute_column_coverage(column_name=column.name, yaml_model=yaml_model)
        for column in _merged_columns(node.columns, catalog_node)
    ]

    return ModelCoverage(
        name=node.name,
        unique_id=node.unique_id,
        layer=layer,
        has_model_description=(
            is_description_set(yaml_model.description) if yaml_model is not None else False
        ),
        columns=columns,
    )


def _compute_column_coverage(
    *,
    column_name: str,
    yaml_model: YamlModel | None,
) -> ColumnCoverage:
    yaml_column = yaml_model.columns.get(column_name) if yaml_model is not None else None
    return ColumnCoverage(
        name=column_name,
        has_description=(
            is_description_set(yaml_column.description) if yaml_column is not None else False
        ),
        test_count=len(yaml_column.tests) if yaml_column is not None else 0,
    )


def _merged_columns(
    manifest_columns: dict[str, ManifestColumn],
    catalog_node: CatalogNode | None,
) -> list[ManifestColumn]:
    columns = list(manifest_columns.values())
    seen_column_names = {column.name.lower() for column in columns}

    if catalog_node is None:
        return columns

    for catalog_column in catalog_node.columns:
        if catalog_column.name.lower() in seen_column_names:
            continue
        seen_column_names.add(catalog_column.name.lower())
        columns.append(
            ManifestColumn(
                name=catalog_column.name,
                data_type=catalog_column.data_type,
                description=catalog_column.comment,
            )
        )

    return columns


def _project_name(config: ScribeConfig, nodes: list[ManifestNode]) -> str:
    raw_project_name: object = getattr(config, "project_name", None)
    if isinstance(raw_project_name, str) and raw_project_name:
        return raw_project_name
    if nodes and nodes[0].fqn:
        return nodes[0].fqn[0]
    return "unknown"


def _adapter(nodes: list[ManifestNode]) -> str:
    if not nodes:
        return "unknown"
    if nodes[0].adapter_type:
        return nodes[0].adapter_type
    if nodes[0].fqn:
        return nodes[0].fqn[0]
    return "unknown"
