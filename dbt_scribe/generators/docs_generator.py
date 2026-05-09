from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from dbt_scribe.analyzer import EnrichedModel, Layer
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.base_generator import LLMProvider


@dataclass(frozen=True)
class DocsResult:
    model_description: str
    docs_block_content: str
    columns: dict[str, str]


def generate_docs(
    model: EnrichedModel,
    provider: LLMProvider,
    config: ScribeConfig,
) -> DocsResult:
    prompt = _render_prompt(_template_for_layer(model.layer), model=model, config=config)
    response = provider.complete(_system_prompt(), prompt)
    payload = _parse_json_response(response.content)

    return DocsResult(
        model_description=payload.get("model_description", ""),
        docs_block_content=payload.get("docs_block_content", ""),
        columns=dict(payload.get("columns", {})),
    )


def _template_for_layer(layer: Layer) -> str:
    if layer is Layer.INTERMEDIATE:
        return "docs_intermediate.j2"
    if layer is Layer.MARTS:
        return "docs_mart.j2"
    return "docs_staging.j2"


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
        "You generate dbt documentation. Return JSON only: no markdown fences, "
        "no commentary, no preamble."
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
    # Strip markdown code fences if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        # Remove closing fence
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
