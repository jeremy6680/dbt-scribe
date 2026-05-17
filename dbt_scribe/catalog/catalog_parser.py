from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import cast


@dataclass
class CatalogColumn:
    """A column extracted from dbt's catalog.json file."""

    name: str
    data_type: str
    comment: str


@dataclass
class CatalogNode:
    """A dbt model node extracted from dbt's catalog.json file."""

    unique_id: str
    name: str
    columns: list[CatalogColumn]


def _as_mapping(value: object) -> Mapping[str, object]:
    """Return a string-keyed mapping when the JSON value is an object."""
    if isinstance(value, dict):
        return cast("Mapping[str, object]", value)
    return {}


def _string_or_empty(value: object) -> str:
    """Return a string value or an empty string for missing and null values."""
    if isinstance(value, str):
        return value
    return ""


def _parse_columns(raw_columns: object) -> list[CatalogColumn]:
    """Parse catalog column objects into typed columns."""
    columns: list[CatalogColumn] = []
    for column_key, raw_column in _as_mapping(raw_columns).items():
        column = _as_mapping(raw_column)
        raw_name = column.get("name", column_key)
        name = _string_or_empty(raw_name).lower()
        data_type = _string_or_empty(column.get("type", ""))
        comment = _string_or_empty(column.get("comment", ""))
        columns.append(
            CatalogColumn(
                name=name,
                data_type=data_type,
                comment=comment,
            )
        )
    return columns


def parse_catalog(catalog_path: Path) -> dict[str, CatalogNode] | None:
    """Parse target/catalog.json and return a dict keyed by unique_id.

    Returns None if the file does not exist, so callers can gracefully fall
    back to manifest-only mode without raising.

    Only nodes whose unique_id starts with "model." are included.
    """
    if not catalog_path.exists():
        return None

    try:
        with catalog_path.open(encoding="utf-8") as catalog_file:
            raw_catalog: object = json.load(catalog_file)
    except JSONDecodeError as error:
        raise ValueError(f"catalog.json is not valid JSON: {error}") from error

    catalog = _as_mapping(raw_catalog)
    parsed_nodes: dict[str, CatalogNode] = {}

    for raw_node in _as_mapping(catalog.get("nodes", {})).values():
        node = _as_mapping(raw_node)
        unique_id = _string_or_empty(node.get("unique_id", ""))
        if not unique_id.startswith("model."):
            continue

        parsed_nodes[unique_id] = CatalogNode(
            unique_id=unique_id,
            name=_string_or_empty(node.get("name", "")),
            columns=_parse_columns(node.get("columns", {})),
        )

    return parsed_nodes
