from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManifestColumn:
    name: str
    data_type: str | None
    description: str | None


@dataclass(frozen=True)
class ManifestNode:
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


def parse_manifest(manifest_path: str | Path) -> list[ManifestNode]:
    """Parse dbt's compiled manifest and return model nodes only."""
    path = Path(manifest_path)
    with path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    adapter_type = manifest.get("metadata", {}).get("adapter_type")
    nodes = manifest.get("nodes", {})

    parsed_nodes: list[ManifestNode] = []
    for raw_node in nodes.values():
        if raw_node.get("resource_type") != "model":
            continue

        columns = {
            column_name: ManifestColumn(
                name=column.get("name", column_name),
                data_type=column.get("data_type"),
                description=column.get("description"),
            )
            for column_name, column in raw_node.get("columns", {}).items()
        }
        config = raw_node.get("config", {})

        parsed_nodes.append(
            ManifestNode(
                unique_id=raw_node["unique_id"],
                name=raw_node["name"],
                fqn=list(raw_node.get("fqn", [])),
                resource_type=raw_node["resource_type"],
                compiled_code=raw_node.get("compiled_code") or raw_node.get("compiled_sql") or "",
                columns=columns,
                depends_on_nodes=list(raw_node.get("depends_on", {}).get("nodes", [])),
                tags=list(config.get("tags", [])),
                materialized=config.get("materialized"),
                path=raw_node.get("path", ""),
                adapter_type=adapter_type,
                config=dict(config),
            )
        )

    return parsed_nodes
