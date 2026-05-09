from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import sqlglot
from sqlglot import exp

from dbt_scribe.config import ConventionsConfig, ScribeConfig, TestsConfig
from dbt_scribe.parsers.manifest_parser import ManifestNode
from dbt_scribe.parsers.yaml_parser import YamlModel, is_description_set


class Layer(Enum):
    STAGING = "staging"
    INTERMEDIATE = "intermediate"
    MARTS = "marts"
    UNKNOWN = "unknown"


class ColumnType(Enum):
    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    ENUM = "enum"
    SHARED = "shared"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    METRIC = "metric"
    CALCULATED = "calculated"
    TEXT = "text"


@dataclass(frozen=True)
class EnrichedColumn:
    name: str
    data_type: str | None
    description: str | None
    tests: list[Any]
    column_type: ColumnType
    sql_expression: str | None
    needs_doc: bool
    needs_tests: bool


@dataclass(frozen=True)
class EnrichedModel:
    unique_id: str
    name: str
    fqn: list[str]
    layer: Layer
    description: str | None
    compiled_code: str
    columns: dict[str, EnrichedColumn]
    depends_on_nodes: list[str]
    tags: list[str]
    materialized: str | None
    path: str
    adapter_type: str | None


AGGREGATION_PATTERN = re.compile(
    r"\b(count|sum|avg|min|max|median)\s*\(", re.IGNORECASE
)
ARITHMETIC_PATTERN = re.compile(r"\s[+\-*/]\s")


def detect_layer(fqn: list[str], config: ConventionsConfig) -> Layer:
    """Detect the dbt layer from a node's fully-qualified name.

    Matches fqn[1] against configured layer prefixes. Also accepts common
    alternate spellings (e.g. 'mart' for 'marts') to avoid silent failures
    when the project folder name differs slightly from the config value.

    Args:
        fqn: Fully-qualified node name list from the manifest.
        config: Conventions config containing layer folder names.

    Returns:
        The detected Layer enum value, or Layer.UNKNOWN if unrecognised.
    """
    if len(fqn) < 2:
        return Layer.UNKNOWN

    layer_name = fqn[1]

    # Exact match first
    if layer_name == config.staging_prefix:
        return Layer.STAGING
    if layer_name == config.intermediate_prefix:
        return Layer.INTERMEDIATE
    if layer_name == config.marts_prefix:
        return Layer.MARTS

    # Common alternate spellings — mart vs marts
    if layer_name in ("mart", "marts", "mrt"):
        return Layer.MARTS
    if layer_name in ("staging", "stage", "stg"):
        return Layer.STAGING
    if layer_name in ("intermediate", "int"):
        return Layer.INTERMEDIATE

    return Layer.UNKNOWN


def _find_primary_key_column(
    column_names: list[str],
    config: TestsConfig,
) -> str | None:
    """Return the name of the most likely primary key column, or None.

    A column is considered the primary key only when it is the sole column
    matching pk_patterns. When multiple columns match (e.g. order_id and
    user_id in an orders table), none is a true PK — they are foreign keys
    and should be typed accordingly.

    Args:
        column_names: Ordered list of column names from the model.
        config: Tests config containing pk_patterns.

    Returns:
        The PK column name if exactly one column matches, otherwise None.
    """
    pk_candidates = [
        name for name in column_names
        if _matches_any(name, config.pk_patterns)
    ]
    # Only treat as PK when there is exactly one candidate — unambiguous
    return pk_candidates[0] if len(pk_candidates) == 1 else None


def infer_column_type(
    column_name: str,
    sql_expression: str | None,
    config: TestsConfig,
    *,
    shared_columns: list[str] | None = None,
    pk_column: str | None = None,
) -> ColumnType:
    """Infer the semantic type of a column from its name, SQL expression, and config.

    Applies a priority cascade — the first matching rule wins:
    1. Exact PK match (only when pk_column is set — i.e. unambiguous single PK)
    2. FK patterns from config
    3. PK patterns not designated as PK → FK (e.g. order_id in a multi-key model)
    4. Enum patterns from config
    5. Shared columns list from docs config
    6. Boolean name heuristics (is_, has_, did_)
    7. Timestamp name heuristics (_at, _date)
    8. Metric (aggregation in SQL expression)
    9. Calculated (arithmetic in SQL expression)
    10. Default: text

    Args:
        column_name: The column name to classify.
        sql_expression: The SQL expression for this column if computed, else None.
        config: Tests config with pk/fk/enum patterns.
        shared_columns: List of shared column names from docs config.
        pk_column: The designated PK column name for this model, or None.

    Returns:
        The inferred ColumnType.
    """
    # Rule 1 — designated primary key (unambiguous single PK)
    if pk_column and column_name == pk_column:
        return ColumnType.PRIMARY_KEY

    # Rule 2 — explicit FK patterns (e.g. customer_fk)
    if _matches_any(column_name, config.fk_patterns):
        return ColumnType.FOREIGN_KEY

    # Rule 3 — matches pk_patterns but NOT the designated PK → treat as FK
    # Example: user_id in an orders table where order_id is the PK
    if _matches_any(column_name, config.pk_patterns):
        return ColumnType.FOREIGN_KEY

    # Rule 4 — enum patterns
    if _matches_any(column_name, config.enum_patterns):
        return ColumnType.ENUM

    # Rule 5 — shared columns
    if shared_columns and column_name in shared_columns:
        return ColumnType.SHARED

    # Rule 6 — boolean heuristics
    if column_name.startswith(("is_", "has_", "did_")):
        return ColumnType.BOOLEAN

    # Rule 7 — timestamp heuristics
    if column_name.endswith(("_at", "_date")):
        return ColumnType.TIMESTAMP

    # Rule 8 — metric (aggregation function in SQL expression)
    if sql_expression and AGGREGATION_PATTERN.search(sql_expression):
        return ColumnType.METRIC

    # Rule 9 — calculated (arithmetic in SQL expression)
    if sql_expression and ARITHMETIC_PATTERN.search(sql_expression):
        return ColumnType.CALCULATED

    # Rule 10 — default
    return ColumnType.TEXT


def build_enriched_model(
    node: ManifestNode,
    yaml_model: YamlModel | None,
    config: ScribeConfig,
    *,
    overwrite_existing: bool = False,
) -> EnrichedModel:
    """Build an EnrichedModel from a manifest node and existing YAML state.

    Combines manifest metadata, existing YAML documentation and tests, compiled
    SQL expressions, and generation flags (needs_doc, needs_tests) into a single
    object consumed by the generators and writers.

    Args:
        node: Parsed manifest node for this model.
        yaml_model: Existing YAML state for this model, or None if no YAML exists.
        config: Project-level dbt-scribe configuration.
        overwrite_existing: When True, sets needs_doc and needs_tests to True
            even for columns that already have descriptions or tests.

    Returns:
        A fully populated EnrichedModel instance.
    """
    expressions = _extract_select_expressions(node.compiled_code, node.adapter_type)
    yaml_columns = yaml_model.columns if yaml_model else {}

    # Determine the unambiguous PK column for this model before typing columns
    pk_column = _find_primary_key_column(
        list(node.columns.keys()), config.tests
    )

    columns = {}
    for column_name, manifest_column in node.columns.items():
        yaml_column = yaml_columns.get(column_name)
        description = (
            yaml_column.description
            if yaml_column and yaml_column.description is not None
            else manifest_column.description
        )
        tests = list(yaml_column.tests) if yaml_column else []
        sql_expression = expressions.get(column_name)

        columns[column_name] = EnrichedColumn(
            name=column_name,
            data_type=manifest_column.data_type,
            description=description,
            tests=tests,
            column_type=infer_column_type(
                column_name,
                sql_expression,
                config.tests,
                shared_columns=config.docs.shared_columns,
                pk_column=pk_column,
            ),
            sql_expression=sql_expression,
            needs_doc=overwrite_existing or not is_description_set(description),
            needs_tests=overwrite_existing or not tests,
        )

    return EnrichedModel(
        unique_id=node.unique_id,
        name=node.name,
        fqn=node.fqn,
        layer=detect_layer(node.fqn, config.conventions),
        description=yaml_model.description if yaml_model else None,
        compiled_code=node.compiled_code,
        columns=columns,
        depends_on_nodes=node.depends_on_nodes,
        tags=node.tags,
        materialized=node.materialized,
        path=node.path,
        adapter_type=node.adapter_type,
    )


def _matches_any(value: str, patterns: list[str]) -> bool:
    """Return True if value matches any of the given regex patterns.

    Args:
        value: String to test.
        patterns: List of regex pattern strings.

    Returns:
        True if any pattern matches.
    """
    return any(re.match(pattern, value) for pattern in patterns)


def _extract_select_expressions(
    compiled_code: str,
    adapter_type: str | None,
) -> dict[str, str]:
    """Extract column name → SQL expression mappings from compiled SQL.

    Uses sqlglot to parse the compiled SQL and extract the expression for
    each selected column. Falls back to a regex-based approach if sqlglot
    fails to parse the SQL.

    Args:
        compiled_code: Fully compiled SQL string (Jinja2 already resolved).
        adapter_type: dbt adapter name used as the sqlglot read dialect.

    Returns:
        Dict mapping column alias/name to its SQL expression string.
    """
    try:
        tree = sqlglot.parse_one(compiled_code, read=adapter_type or None)
    except sqlglot.errors.SqlglotError:
        return _extract_select_expressions_fallback(compiled_code)

    expressions: dict[str, str] = {}
    for select in tree.find_all(exp.Select):
        for select_expression in select.expressions:
            alias = select_expression.alias_or_name
            if alias:
                expressions[alias] = (
                    select_expression.this.sql()
                    if isinstance(select_expression, exp.Alias)
                    else select_expression.sql()
                )
    return expressions


def _extract_select_expressions_fallback(compiled_code: str) -> dict[str, str]:
    """Regex-based fallback for SQL expression extraction when sqlglot fails.

    Args:
        compiled_code: Fully compiled SQL string.

    Returns:
        Dict mapping column alias/name to its SQL expression string.
    """
    expressions: dict[str, str] = {}
    for expression, alias in re.findall(
        r"(?im)^\s*(.+?)\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*,?$",
        compiled_code,
    ):
        expressions[alias] = expression.strip()
    for column in re.findall(
        r"(?im)^\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*,?$", compiled_code
    ):
        expressions[column.split(".")[-1]] = column.strip()
    return expressions