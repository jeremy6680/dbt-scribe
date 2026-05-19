from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from dbt_scribe.analyzer import EnrichedModel
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.generators.tests_generator import TestsResult
from dbt_scribe.parsers.yaml_parser import is_description_set

# Round-trip YAML instance — preserves comments and formatting on existing files.
_RUAMEL_YAML = YAML(typ="rt")
_RUAMEL_YAML.indent(mapping=2, sequence=4, offset=2)
_RUAMEL_YAML.default_flow_style = False
_RUAMEL_YAML.width = 4096
_RUAMEL_YAML.preserve_quotes = True

# Clean YAML instance for writing brand-new files from scratch.
_RUAMEL_YAML_CLEAN = YAML()
_RUAMEL_YAML_CLEAN.indent(mapping=2, sequence=4, offset=2)
_RUAMEL_YAML_CLEAN.default_flow_style = False
_RUAMEL_YAML_CLEAN.width = 4096


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
    """Write or merge dbt model documentation and tests into a YAML file.

    Args:
        model: Enriched model with column metadata.
        docs_result: LLM-generated descriptions.
        tests_result: LLM-generated tests.
        config: dbt-scribe configuration.
        dry_run: When True, compute changes but do not write to disk.
        force: When True, overwrite existing descriptions and tests.
        source_path: Path to an existing shared YAML file that already
            declares this model. When provided and the file exists, the
            model entry is merged in-place and the file is rewritten
            only if the model entry actually changed (semantic comparison).
            When None, a per-model file is derived from model.path.

    Returns:
        WriterResult with the resolved path, whether changes occurred,
        and the serialised content (new files only).
    """
    # Resolve the target path: shared file if it exists, per-model otherwise.
    is_shared_file = source_path is not None and source_path.exists()
    path: Path = (
        source_path
        if (is_shared_file and source_path is not None)
        else _model_yaml_path(model, config.model_root)
    )

    data = _load_yaml(path)
    model_yaml = _find_or_create_model(data, model)

    # Snapshot the model entry *before* merge for semantic change detection.
    # This avoids false positives from YAML formatting differences (ruamel
    # round-trip vs. hand-written or PyYAML-written files).
    snapshot_before = _model_snapshot(model_yaml)

    _merge_model_description(model_yaml, docs_result, force=force)
    _merge_columns(model_yaml, model, docs_result, tests_result, force=force)

    snapshot_after = _model_snapshot(model_yaml)
    changed = snapshot_before != snapshot_after

    if not dry_run and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        if is_shared_file:
            # Rewrite only the model entry inside the existing shared file.
            # All other model entries, comments, and formatting are preserved
            # by ruamel round-trip mode.
            _rewrite_shared_file(path, data)
        else:
            # New or per-model file: dump via clean YAML instance.
            # Use data directly (not _to_plain_dict) so that ruamel
            # CommentedMap inline comments (e.g. TODO on accepted_values)
            # are preserved in the output.
            stream = StringIO()
            _RUAMEL_YAML_CLEAN.dump(data, stream)
            path.write_text(stream.getvalue())

    content = None if is_shared_file else _dump_for_content(data)
    return WriterResult(path=path.resolve(), changed=changed, content=content)


def _rewrite_shared_file(path: Path, data: Any) -> None:
    """Rewrite a shared YAML file using ruamel round-trip to preserve
    comments and formatting outside the modified model entry."""
    stream = StringIO()
    _RUAMEL_YAML.dump(data, stream)
    path.write_text(stream.getvalue())


def _dump_for_content(data: Any) -> str:
    """Serialise data to a YAML string for WriterResult.content.

    Uses the clean YAML instance and dumps data directly (preserving
    ruamel inline comments such as TODO markers on accepted_values tests).
    """
    stream = StringIO()
    _RUAMEL_YAML_CLEAN.dump(data, stream)
    return stream.getvalue()


def _model_snapshot(model_yaml: Any) -> str:
    """Return a stable JSON string representing the model entry's logical
    content, used for semantic change detection independent of YAML formatting.

    ruamel CommentedMap/CommentedSeq are converted to plain Python structures
    before serialisation so that formatting metadata does not affect equality.
    """
    return json.dumps(_to_plain_dict(model_yaml), sort_keys=True, ensure_ascii=False)


def _to_plain_dict(obj: Any) -> Any:
    """Recursively convert ruamel CommentedMap/CommentedSeq to plain
    Python dicts and lists, used for semantic snapshot comparison only."""
    if isinstance(obj, (CommentedMap, dict)):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, (CommentedSeq, list)):
        return [_to_plain_dict(v) for v in obj]
    return obj


def _model_yaml_path(model: EnrichedModel, model_root: str = "models") -> Path:
    """Return the conventional per-model YAML path derived from model.path."""
    return Path(model_root) / Path(model.path).with_suffix(".yml")


def _load_yaml(path: Path) -> Any:
    """Load a YAML file with ruamel round-trip parser, or return a default
    empty structure if the file does not exist."""
    if not path.exists():
        return {"version": 2, "models": []}
    return _RUAMEL_YAML.load(path.read_text()) or {"version": 2, "models": []}


def _find_or_create_model(data: Any, model: EnrichedModel) -> Any:
    """Find the model entry by name in data['models'], or append a new one.

    Works correctly on both CommentedMap (ruamel) and plain dict structures.
    """
    data.setdefault("version", 2)
    models = data.setdefault("models", [])
    for model_yaml in models:
        if model_yaml.get("name") == model.name:
            model_yaml.setdefault("columns", [])
            return model_yaml

    new_entry: dict[str, Any] = {
        "name": model.name,
        "description": "",
        "columns": [],
    }
    if model.tags:
        new_entry["config"] = {"tags": model.tags}
    models.append(new_entry)
    return new_entry


def _merge_model_description(
    model_yaml: Any,
    docs_result: DocsResult,
    *,
    force: bool,
) -> None:
    """Merge the generated model description unless already set and not forced."""
    if force or not is_description_set(model_yaml.get("description")):
        model_yaml["description"] = docs_result.model_description


def _merge_columns(
    model_yaml: Any,
    model: EnrichedModel,
    docs_result: DocsResult,
    tests_result: TestsResult,
    *,
    force: bool,
) -> None:
    """Merge generated column descriptions and tests non-destructively."""
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


def _migrate_tests_key(column_yaml: Any) -> None:
    """Migrate legacy 'tests' key to 'data_tests' in place."""
    if "tests" in column_yaml and "data_tests" not in column_yaml:
        column_yaml["data_tests"] = column_yaml.pop("tests")

def _append_missing_tests(column_yaml: Any, generated_tests: list[Any]) -> None:
    """Append generated tests that are not already present.
    
    Deduplication is based on test type (the top-level key for dict tests,
    or the string value for simple tests), not on full dict equality.
    This prevents adding duplicate tests when the existing test has extra
    keys such as `config`, `name`, or `severity` that the LLM does not generate.
    """
    tests = column_yaml.setdefault("data_tests", [])
    existing_types = _existing_test_types(tests)
    for test in generated_tests:
        test_type = _test_type(test)
        if test_type not in existing_types:
            tests.append(_with_accepted_values_todo(test))
            existing_types.add(test_type)


def _test_type(test: Any) -> str:
    """Return a stable string key identifying the type of a test.
    
    For simple tests (e.g. 'unique', 'not_null'): returns the string itself.
    For dict tests (e.g. {'accepted_values': {...}}): returns the top-level key.
    """
    if isinstance(test, str):
        return test
    if isinstance(test, dict) and test:
        return next(iter(test))
    return repr(test)


def _existing_test_types(tests: list[Any]) -> set[str]:
    """Return the set of test types already present in a column's test list."""
    return {_test_type(t) for t in tests}

def _with_accepted_values_todo(test: Any) -> Any:
    """Add a TODO comment to accepted_values tests with an empty values list."""
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