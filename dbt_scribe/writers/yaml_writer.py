from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dbt_scribe.analyzer import EnrichedModel
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult
from dbt_scribe.parsers.yaml_parser import is_description_set


@dataclass(frozen=True)
class WriterResult:
    path: Path
    changed: bool
    content: str | None = None


def write_yaml(
    model: EnrichedModel,
    docs_result: DocsResult,
    tests_result: TestsResult,
    config: ScribeConfig,
    dry_run: bool,
    *,
    force: bool = False,
) -> WriterResult:
    path = _model_yaml_path(model)
    data = _load_yaml(path)
    model_yaml = _find_or_create_model(data, model)

    _merge_model_description(model_yaml, docs_result, force=force)
    _merge_columns(model_yaml, model, docs_result, tests_result, force=force)

    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return WriterResult(path=path.resolve(), changed=True, content=content)


def _model_yaml_path(model: EnrichedModel) -> Path:
    return Path("models") / Path(model.path).with_suffix(".yml")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 2, "models": []}
    return yaml.safe_load(path.read_text()) or {"version": 2, "models": []}


def _find_or_create_model(data: dict[str, Any], model: EnrichedModel) -> dict[str, Any]:
    data.setdefault("version", 2)
    models = data.setdefault("models", [])
    for model_yaml in models:
        if model_yaml.get("name") == model.name:
            model_yaml.setdefault("columns", [])
            return model_yaml

    model_yaml = {
        "name": model.name,
        "description": "",
        "columns": [],
    }
    if model.tags:
        model_yaml["config"] = {"tags": model.tags}
    models.append(model_yaml)
    return model_yaml


def _merge_model_description(
    model_yaml: dict[str, Any],
    docs_result: DocsResult,
    *,
    force: bool,
) -> None:
    if force or not is_description_set(model_yaml.get("description")):
        model_yaml["description"] = docs_result.model_description


def _merge_columns(
    model_yaml: dict[str, Any],
    model: EnrichedModel,
    docs_result: DocsResult,
    tests_result: TestsResult,
    *,
    force: bool,
) -> None:
    existing_columns = {
        column.get("name"): column for column in model_yaml.setdefault("columns", [])
    }
    for column_name in model.columns:
        column_yaml = existing_columns.get(column_name)
        if column_yaml is None:
            column_yaml = {"name": column_name, "description": ""}
            model_yaml["columns"].append(column_yaml)
            existing_columns[column_name] = column_yaml

        generated_description = docs_result.columns.get(column_name)
        if generated_description and (
            force or not is_description_set(column_yaml.get("description"))
        ):
            column_yaml["description"] = generated_description

        generated_tests = tests_result.columns.get(column_name, [])
        if generated_tests:
            _append_missing_tests(column_yaml, generated_tests)


def _append_missing_tests(column_yaml: dict[str, Any], generated_tests: list[Any]) -> None:
    tests = column_yaml.setdefault("data_tests", column_yaml.pop("tests", []))
    for test in generated_tests:
        if test not in tests:
            tests.append(test)
