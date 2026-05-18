from __future__ import annotations

import copy
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from dbt_scribe.analyzer import EnrichedModel
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult
from dbt_scribe.parsers.yaml_parser import is_description_set

_RUAMEL_YAML = YAML(typ="rt")
_RUAMEL_YAML.indent(mapping=2, sequence=4, offset=2)
_RUAMEL_YAML.default_flow_style = False


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
    source_path: Path | None = None,
) -> WriterResult:
    path = (
        source_path
        if source_path is not None and source_path.exists()
        else _model_yaml_path(model, config.model_root)
    )
    data = _load_yaml(path)
    model_yaml = _find_or_create_model(data, model)

    _merge_model_description(model_yaml, docs_result, force=force)
    _merge_columns(model_yaml, model, docs_result, tests_result, force=force)

    stream = StringIO()
    _RUAMEL_YAML.dump(data, stream)
    content = stream.getvalue()
    existing_content = path.read_text() if path.exists() else None
    changed = existing_content != content
    if not dry_run and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return WriterResult(path=path.resolve(), changed=changed, content=content)


def _model_yaml_path(model: EnrichedModel, model_root: str = "models") -> Path:
    return Path(model_root) / Path(model.path).with_suffix(".yml")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 2, "models": []}
    return _RUAMEL_YAML.load(path.read_text()) or {"version": 2, "models": []}


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

        _migrate_tests_key(column_yaml)
        generated_tests = tests_result.columns.get(column_name, [])
        if generated_tests:
            _append_missing_tests(column_yaml, generated_tests)


def _migrate_tests_key(column_yaml: dict[str, Any]) -> None:
    if "tests" in column_yaml and "data_tests" not in column_yaml:
        column_yaml["data_tests"] = column_yaml.pop("tests")


def _append_missing_tests(column_yaml: dict[str, Any], generated_tests: list[Any]) -> None:
    tests = column_yaml.setdefault("data_tests", [])
    for test in generated_tests:
        if test not in tests:
            tests.append(_with_accepted_values_todo(test))


def _with_accepted_values_todo(test: Any) -> Any:
    copied_test = copy.deepcopy(test)
    if not isinstance(copied_test, dict):
        return copied_test

    accepted_values = copied_test.get("accepted_values")
    if not isinstance(accepted_values, dict):
        return copied_test

    arguments = accepted_values.get("arguments")
    if not isinstance(arguments, dict) or arguments.get("values") != []:
        return copied_test

    if not isinstance(arguments, CommentedMap):
        arguments = CommentedMap(arguments)
        accepted_values["arguments"] = arguments
    arguments.yaml_add_eol_comment(
        "TODO: fill with actual enum values from source system",
        key="values",
    )
    return copied_test
