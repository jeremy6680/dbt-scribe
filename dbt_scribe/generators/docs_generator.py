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
    """Parsed documentation generation result from the LLM."""

    model_description: str
    docs_block_content: str
    columns: dict[str, str]


def generate_docs(
    model: EnrichedModel,
    provider: LLMProvider,
    config: ScribeConfig,
) -> DocsResult:
    """Generate dbt documentation for a model via the configured LLM provider.

    Calls the LLM once per model with a layer-specific prompt, parses the JSON
    response, and assembles the final DocsResult. For mart models, the four-section
    docs block is assembled in Python from separate LLM fields to guarantee the
    structure regardless of LLM behaviour.

    Args:
        model: Enriched model with typed columns and needs_doc flags.
        provider: Configured LLM provider instance.
        config: Project-level dbt-scribe configuration.

    Returns:
        DocsResult with model description, docs block content, and column descriptions.
    """
    prompt = _render_prompt(
        _template_for_layer(model.layer), model=model, config=config
    )
    response = provider.complete(_system_prompt(), prompt)
    payload = _parse_json_response(response.content)

    docs_block_content = (
        _assemble_mart_docs_block(payload, config)
        if model.layer is Layer.MARTS
        else payload.get("docs_block_content", "")
    )

    return DocsResult(
        model_description=payload.get("model_description", ""),
        docs_block_content=docs_block_content,
        columns=dict(payload.get("columns", {})),
    )


def _assemble_mart_docs_block(payload: dict, config: ScribeConfig) -> str:
    """Assemble the four-section mart docs block from separate LLM response fields.

    Building the structure in Python guarantees the four-section template is always
    respected, regardless of whether the LLM follows the prompt instructions.

    Accepts two possible LLM response shapes:
    - Preferred: separate ``description_and_motivation`` and ``known_limitations`` fields
    - Fallback: a single ``docs_block_content`` field (LLM ignored the prompt structure)

    Sections:
        1. Description and Motivation
        2. Known Limitations
        3. Business Stakeholder — from config
        4. Technical Stakeholder — from config

    Args:
        payload: Parsed JSON response from the LLM.
        config: Project-level dbt-scribe configuration used for stakeholder fields.

    Returns:
        Formatted four-section markdown string.
    """
    # Preferred shape — separate fields
    description = payload.get("description_and_motivation", "").strip()
    limitations = payload.get("known_limitations", "").strip()

    # Fallback — LLM returned docs_block_content instead of separate fields
    if not description:
        raw = payload.get("docs_block_content", "").strip()
        description = raw or "No description generated."

    if not limitations:
        limitations = "None identified."

    stakeholder = config.docs.default_owner or "TBD"

    sections = [
        "# Description and Motivation",
        "",
        description,
        "",
        "# Known Limitations",
        "",
        limitations,
        "",
        "# Business Stakeholder",
        "",
        stakeholder,
        "",
        "# Technical Stakeholder",
        "",
        stakeholder,
    ]
    return "\n".join(sections)


def _template_for_layer(layer: Layer) -> str:
    """Return the Jinja2 prompt template filename for the given layer.

    Args:
        layer: The detected dbt layer for this model.

    Returns:
        Template filename string.
    """
    if layer is Layer.INTERMEDIATE:
        return "docs_intermediate.j2"
    if layer is Layer.MARTS:
        return "docs_mart.j2"
    return "docs_staging.j2"


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
    """Return the system prompt for the docs generation LLM call."""
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