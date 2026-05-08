from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from dbt_scribe.analyzer import ColumnType, EnrichedModel
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.base_generator import LLMProvider


@dataclass(frozen=True)
class TestsResult:
    columns: dict[str, list[Any]]


def generate_tests(
    model: EnrichedModel,
    provider: LLMProvider,
    config: ScribeConfig,
) -> TestsResult:
    prompt = _render_prompt("tests_generic.j2", model=model, config=config)
    response = provider.complete(_system_prompt(), prompt)
    payload = _parse_json_response(response.content)
    columns = {name: list(tests) for name, tests in payload.get("columns", {}).items()}

    _ensure_primary_key_tests(model, columns)
    _ensure_enum_placeholders(model, columns)
    return TestsResult(columns=columns)


def _ensure_primary_key_tests(model: EnrichedModel, columns: dict[str, list[Any]]) -> None:
    for column in model.columns.values():
        if column.column_type is not ColumnType.PRIMARY_KEY:
            continue
        tests = columns.setdefault(column.name, [])
        not_null = next(
            (t for t in tests if _has_test([t], "not_null")),
            {"not_null": {"name": f"not_null_{model.name}_{column.name}"}},
        )
        unique = next(
            (t for t in tests if _has_test([t], "unique")),
            {"unique": {"name": f"unique_{model.name}_{column.name}"}},
        )
        remaining = [t for t in tests if not _has_test([t], "not_null") and not _has_test([t], "unique")]
        tests.clear()
        tests.extend([not_null, unique] + remaining)


def _ensure_enum_placeholders(model: EnrichedModel, columns: dict[str, list[Any]]) -> None:
    for column in model.columns.values():
        if column.column_type is not ColumnType.ENUM:
            continue
        tests = columns.setdefault(column.name, [])
        if not _has_test(tests, "accepted_values"):
            tests.append(
                {
                    "accepted_values": {
                        "name": f"accepted_values_{model.name}_{column.name}",
                        "values": [],
                    }
                }
            )


def _prepend_missing_named_test(tests: list[Any], test: dict[str, Any], name: str) -> None:
    if not _has_test(tests, name):
        tests.insert(0, test)


def _has_test(tests: list[Any], name: str) -> bool:
    for test in tests:
        if test == name:
            return True
        if isinstance(test, dict) and name in test:
            return True
    return False


def _render_prompt(template_name: str, **context: object) -> str:
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template(template_name).render(**context)


def _system_prompt() -> str:
    return (
        "You generate dbt generic tests. Return JSON only: no markdown fences, "
        "no commentary, no preamble."
    )


def _parse_json_response(content: str) -> dict:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a valid JSON object")
    return payload
