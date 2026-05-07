from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


DOC_REFERENCE_PATTERN = re.compile(r"{{\s*doc\s*\(", re.IGNORECASE)


def parse_yaml(yaml_path: str | Path) -> YamlModel | None:
    """Parse an existing dbt model YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as yaml_file:
        data = yaml.safe_load(yaml_file) or {}

    models = data.get("models") or []
    if not models:
        return None

    model = models[0]
    columns = {
        column["name"]: YamlColumn(
            name=column["name"],
            description=column.get("description"),
            tests=list(column.get("data_tests") or column.get("tests") or []),
        )
        for column in model.get("columns", [])
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
