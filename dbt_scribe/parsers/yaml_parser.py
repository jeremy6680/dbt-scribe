from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_SAFE_YAML = YAML(typ="safe")


@dataclass(frozen=True)
class YamlColumn:
    name: str
    description: str | None
    tests: list[Any]


@dataclass(frozen=True)
class YamlModel:
    name: str
    description: str | None
    columns: dict[str, YamlColumn]


@dataclass(frozen=True)
class YamlSource:
    model: YamlModel
    path: Path


DOC_REFERENCE_PATTERN = re.compile(r"{{\s*doc\s*\(", re.IGNORECASE)


def parse_yaml(yaml_path: str | Path) -> YamlModel | None:
    """Parse an existing dbt model YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as yaml_file:
        data = _SAFE_YAML.load(yaml_file) or {}

    models = data.get("models") or []
    if not models:
        return None

    return _parse_model(models[0])


def find_yaml_source(
    model_name: str,
    model_dir: Path,
    model_root: Path,
) -> YamlSource | None:
    """Search for an existing YAML declaration for model_name.

    Scans all .yml files in model_dir, then walks up ancestor directories until
    model_root is reached. Returns the first YamlSource whose model.name matches
    model_name, or None if not found.

    Args:
        model_name: The dbt model name to look for.
        model_dir: Directory containing the model .sql file.
        model_root: Project model root (search stops here).

    Returns:
        YamlSource with the matched model and its file path, or None if no
        existing declaration is found.
    """
    root = model_root.resolve()
    current = model_dir.resolve()

    while current == root or root in current.parents:
        for yaml_path in sorted(current.glob("*.yml")):
            for yaml_model in _parse_models(yaml_path):
                if yaml_model.name == model_name:
                    return YamlSource(model=yaml_model, path=yaml_path)

        if current == root:
            break
        current = current.parent

    return None


def _parse_models(yaml_path: Path) -> list[YamlModel]:
    if not yaml_path.exists():
        return []

    try:
        data = _SAFE_YAML.load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []

    return [
        _parse_model(model)
        for model in data.get("models", [])
        if isinstance(model, dict) and model.get("name")
    ]


def _parse_model(model: dict[str, Any]) -> YamlModel:
    columns = {
        column["name"]: YamlColumn(
            name=column["name"],
            description=column.get("description"),
            tests=list(column.get("data_tests") or column.get("tests") or []),
        )
        for column in model.get("columns", [])
        if column.get("name")
    }

    return YamlModel(
        name=model["name"],
        description=model.get("description"),
        columns=columns,
    )


def is_description_set(description: str | None) -> bool:
    """Return whether a YAML description should be treated as already filled."""
    if description is None:
        return False

    stripped_description = description.strip()
    return bool(stripped_description) or bool(DOC_REFERENCE_PATTERN.search(description))
