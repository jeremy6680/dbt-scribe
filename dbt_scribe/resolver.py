from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from dbt_scribe.parsers.manifest_parser import ManifestNode


def resolve_target(target: str | Path, nodes: list[ManifestNode]) -> list[ManifestNode]:
    """Resolve a CLI target path to matching manifest model nodes."""
    target_path = _normalize_target(target)

    if _is_project_root_target(target_path):
        return nodes

    matched_nodes = [
        node for node in nodes if _node_matches_target(node, target_path)
    ]
    if not matched_nodes:
        raise ValueError(f"No manifest model nodes matched target: {target}")
    return matched_nodes


def _normalize_target(target: str | Path) -> Path:
    path = Path(target)
    if path.is_absolute():
        with suppress(ValueError):
            path = path.relative_to(Path.cwd())
    return Path(str(path).rstrip("/"))


def _is_project_root_target(target: Path) -> bool:
    return str(target) in {".", "", "models"}


def _node_matches_target(node: ManifestNode, target: Path) -> bool:
    sql_path = Path("models") / node.path
    yaml_path = sql_path.with_suffix(".yml")
    return (
        target in (sql_path, yaml_path)
        or _is_relative_to(sql_path.parent, target)
        or _is_relative_to(sql_path, target)
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
