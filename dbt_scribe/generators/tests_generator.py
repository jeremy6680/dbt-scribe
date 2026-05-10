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
    """Parsed test generation result from the LLM."""

    columns: dict[str, list[Any]]


def generate_tests(
    model: EnrichedModel,
    provider: LLMProvider,
    config: ScribeConfig,
) -> TestsResult:
    """Generate dbt generic tests for a model via the configured LLM provider.

    Calls the LLM once per model, parses the JSON response, then applies
    deterministic safeguards to ensure PKs always have not_null + unique and
    enum columns always have an accepted_values placeholder.

    Args:
        model: Enriched model with typed columns and needs_tests flags.
        provider: Configured LLM provider instance.
        config: Project-level dbt-scribe configuration.

    Returns:
        TestsResult with a dict mapping column names to lists of test dicts.
    """
    prompt = _render_prompt("tests_generic.j2", model=model, config=config)
    response = provider.complete(_system_prompt(), prompt)
    payload = _parse_json_response(response.content)
    columns = {
        name: list(tests)
        for name, tests in payload.get("columns", {}).items()
    }

    # Sanitize LLM output — remove any non-standard test formats
    columns = {name: _sanitize_tests(tests) for name, tests in columns.items()}

    # Deterministic safeguards regardless of LLM output
    _ensure_primary_key_tests(model, columns)
    _ensure_enum_placeholders(model, columns)

    return TestsResult(columns=columns)


_VALID_TEST_CONFIG_KEYS = {"name", "arguments", "config", "test_name"}


def _sanitize_tests(tests: list[Any]) -> list[Any]:
    """Remove test entries that do not follow the expected dbt dict format,
    and strip unknown keys from test config dicts.

    Valid test: a dict with exactly one key that is a known standard dbt
    generic test type, whose value is a dict containing at least a `name` key.

    Rejects:
    - ``{"test": "not_null"}`` — wrong key
    - ``"not_null"`` — bare string
    - ``{"dbt_utils.expression_is_true": {...}}`` — non-standard test type

    Strips unknown config keys (e.g. ``todo``) that the LLM may hallucinate
    and that dbt would pass as kwargs to the macro, causing a compilation error.

    Args:
        tests: Raw list of test entries from the LLM response.

    Returns:
        Filtered list containing only well-formed standard dbt test dicts.
    """
    valid_types = {"not_null", "unique", "accepted_values", "relationships"}
    sanitized: list[Any] = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        keys = list(test.keys())
        if len(keys) != 1:
            continue
        test_type = keys[0]
        if test_type not in valid_types:
            continue
        config = test.get(test_type)
        if not isinstance(config, dict):
            continue
        clean_config = {k: v for k, v in config.items() if k in _VALID_TEST_CONFIG_KEYS}
        sanitized.append({test_type: clean_config})
    return sanitized


def _ensure_primary_key_tests(
    model: EnrichedModel,
    columns: dict[str, list[Any]],
) -> None:
    """Ensure every primary key column has not_null and unique tests.

    Adds missing tests in canonical order (not_null first, unique second),
    preserving any other existing tests after them.

    Args:
        model: Enriched model containing typed columns.
        columns: Mutable dict of column name → test list, modified in place.
    """
    for column in model.columns.values():
        if column.column_type is not ColumnType.PRIMARY_KEY:
            continue

        tests = columns.setdefault(column.name, [])

        # Snapshot existing state before clearing
        existing_not_null = next(
            (t for t in tests if _has_test([t], "not_null")), None
        )
        existing_unique = next(
            (t for t in tests if _has_test([t], "unique")), None
        )
        other = [
            t for t in tests
            if not _has_test([t], "not_null") and not _has_test([t], "unique")
        ]

        # Build canonical entries — use existing if present, otherwise create new
        not_null = existing_not_null or {
            "not_null": {"name": f"{model.name}_{column.name}_not_null"}
        }
        unique = existing_unique or {
            "unique": {"name": f"{model.name}_{column.name}_unique"}
        }

        # Reconstruct in canonical order: not_null, unique, ...other
        tests.clear()
        tests.append(not_null)
        tests.append(unique)
        tests.extend(other)


def _ensure_enum_placeholders(
    model: EnrichedModel,
    columns: dict[str, list[Any]],
) -> None:
    """Ensure every enum column has an accepted_values test.

    If the LLM did not generate one, appends a placeholder with an empty
    values list and a TODO note, using the dbt >= 1.10.5 arguments format.

    Args:
        model: Enriched model containing typed columns.
        columns: Mutable dict of column name → test list, modified in place.
    """
    for column in model.columns.values():
        if column.column_type is not ColumnType.ENUM:
            continue
        tests = columns.setdefault(column.name, [])
        if not _has_test(tests, "accepted_values"):
            tests.append(
                {
                    "accepted_values": {
                        "name": f"{model.name}_{column.name}_accepted_values",
                        "arguments": {"values": []},
                    }
                }
            )


def _has_test(tests: list[Any], name: str) -> bool:
    """Return True if any entry in tests matches the given test type name.

    Args:
        tests: List of test entries (dicts or strings).
        name: Test type to look for (e.g. "not_null", "unique").

    Returns:
        True if a matching test entry is found.
    """
    for test in tests:
        if test == name:
            return True
        if isinstance(test, dict) and name in test:
            return True
    return False


def _render_prompt(template_name: str, **context: object) -> str:
    """Render a Jinja2 prompt template with the given context.

    Args:
        template_name: Filename of the template in the prompts/ directory.
        **context: Variables passed to the template renderer.

    Returns:
        Rendered prompt string.
    """
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template(template_name).render(**context)


def _system_prompt() -> str:
    """Return the system prompt for the tests generation LLM call."""
    return (
        "You are an analytics engineer generating dbt generic tests. "
        "Return JSON only: no markdown fences, no commentary, no preamble. "
        "Only use standard dbt test types: not_null, unique, accepted_values, relationships. "
        "Never use dbt_utils tests. Never use 'test' as a key. "
        "Every test must be a dict with one key (the test type) whose value is a dict "
        "with a 'name' key. For accepted_values and relationships, put arguments under "
        "an 'arguments' key as per dbt >= 1.10.5 syntax."
    )


def _parse_json_response(content: str) -> dict:
    """Parse and return a JSON response from the LLM.

    Strips markdown code fences (```json ... ```) that some models add
    despite being instructed to return raw JSON only.

    Args:
        content: Raw string response from the LLM provider.

    Returns:
        Parsed dictionary from the JSON response.

    Raises:
        ValueError: If the content cannot be parsed as valid JSON.
    """
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError("LLM returned an empty response")

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response must be valid JSON") from exc
    return payload