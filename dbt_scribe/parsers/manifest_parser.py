from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
import sqlglot.expressions as exp


@dataclass(frozen=True)
class ManifestColumn:
    """A column extracted from the dbt manifest or inferred from compiled SQL."""

    name: str
    data_type: str | None
    description: str | None


@dataclass(frozen=True)
class ManifestNode:
    """A single dbt model node extracted from manifest.json."""

    unique_id: str
    name: str
    fqn: list[str]
    resource_type: str
    compiled_code: str
    columns: dict[str, ManifestColumn]
    depends_on_nodes: list[str]
    tags: list[str]
    materialized: str | None
    path: str
    adapter_type: str | None
    config: dict[str, Any]


# Map dbt adapter names to sqlglot dialect names
_ADAPTER_TO_DIALECT: dict[str, str] = {
    "bigquery": "bigquery",
    "postgres": "postgres",
    "duckdb": "duckdb",
}

# Dialects to try in order when the primary dialect fails
_FALLBACK_DIALECTS: list[str | None] = ["bigquery", "duckdb", "postgres", None]


def _extract_columns_from_sql(
    compiled_sql: str,
    adapter_type: str | None = None,
) -> dict[str, ManifestColumn]:
    """Extract column names from compiled SQL using sqlglot.

    Used as a fallback when the manifest ``columns`` dict is empty (i.e. no
    YAML existed at compile time). Tries the adapter dialect first, then falls
    back through a list of known dialects so that BigQuery backtick quoting and
    other adapter-specific syntax are handled correctly.

    Args:
        compiled_sql: Fully compiled SQL string (Jinja2 already resolved).
        adapter_type: dbt adapter name from manifest metadata (e.g. "bigquery").

    Returns:
        Dict mapping lowercase column name to ManifestColumn, or empty dict if
        parsing fails or the query uses SELECT *.
    """
    if not compiled_sql.strip():
        return {}

    # Build the list of dialects to attempt: adapter dialect first, then fallbacks
    primary = _ADAPTER_TO_DIALECT.get(adapter_type or "", None)
    dialects_to_try: list[str | None] = []
    if primary:
        dialects_to_try.append(primary)
    for d in _FALLBACK_DIALECTS:
        if d not in dialects_to_try:
            dialects_to_try.append(d)

    for dialect in dialects_to_try:
        try:
            statements = sqlglot.parse(compiled_sql, dialect=dialect)
            if not statements:
                continue

            statement = statements[-1]
            if not isinstance(statement, exp.Select):
                continue

            columns: dict[str, ManifestColumn] = {}
            for expression in statement.expressions:
                if isinstance(expression, exp.Alias):
                    col_name = expression.alias.lower()
                elif isinstance(expression, exp.Column):
                    col_name = expression.name.lower()
                elif isinstance(expression, exp.Star):
                    # SELECT * — cannot determine column names statically
                    return {}
                else:
                    # Anonymous expression without alias — skip
                    continue

                if col_name:
                    columns[col_name] = ManifestColumn(
                        name=col_name,
                        data_type=None,
                        description=None,
                    )

            if columns:
                return columns

        except Exception:  # noqa: BLE001 — try next dialect on any parse error
            continue

    return {}


def parse_manifest(manifest_path: str | Path) -> list[ManifestNode]:
    """Parse dbt's compiled manifest and return model nodes only.

    Columns are sourced from the manifest ``columns`` dict when available.
    When that dict is empty (no YAML existed at compile time), column names
    are inferred from the compiled SQL via sqlglot as a fallback.

    Args:
        manifest_path: Path to ``target/manifest.json``.

    Returns:
        List of ManifestNode instances, one per dbt model node.
    """
    path = Path(manifest_path)
    with path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    adapter_type = manifest.get("metadata", {}).get("adapter_type")
    nodes = manifest.get("nodes", {})
    parsed_nodes: list[ManifestNode] = []

    for raw_node in nodes.values():
        if raw_node.get("resource_type") != "model":
            continue

        compiled_code = (
            raw_node.get("compiled_code")
            or raw_node.get("compiled_sql")
            or ""
        )

        # Primary source: columns declared in the manifest (from existing YAML)
        raw_columns = raw_node.get("columns", {})
        if raw_columns:
            columns = {
                column_name: ManifestColumn(
                    name=column.get("name", column_name),
                    data_type=column.get("data_type"),
                    description=column.get("description"),
                )
                for column_name, column in raw_columns.items()
            }
        else:
            # Fallback: extract column names from compiled SQL via sqlglot.
            # Handles the common case where no YAML existed at compile time
            # so dbt left the columns dict empty.
            columns = _extract_columns_from_sql(compiled_code, adapter_type)

        config = raw_node.get("config", {})
        parsed_nodes.append(
            ManifestNode(
                unique_id=raw_node["unique_id"],
                name=raw_node["name"],
                fqn=list(raw_node.get("fqn", [])),
                resource_type=raw_node["resource_type"],
                compiled_code=compiled_code,
                columns=columns,
                depends_on_nodes=list(
                    raw_node.get("depends_on", {}).get("nodes", [])
                ),
                tags=list(config.get("tags", [])),
                materialized=config.get("materialized"),
                path=raw_node.get("path", ""),
                adapter_type=adapter_type,
                config=dict(config),
            )
        )

    return parsed_nodes