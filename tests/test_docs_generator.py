# tests/test_docs_generator.py
from pathlib import Path

import pytest

from dbt_scribe.analyzer import Layer, build_enriched_model
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.base_generator import LLMResponse
from dbt_scribe.generators.docs_generator import DocsResult, generate_docs
from dbt_scribe.parsers.manifest_parser import parse_manifest

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        return LLMResponse(
            content=self.content,
            input_tokens=10,
            output_tokens=5,
            provider="fake",
            model="fake-model",
        )


def _config() -> ScribeConfig:
    return ScribeConfig.model_construct(
        llm=None,
        docs=ScribeConfig.model_fields["docs"].default,
        tests=ScribeConfig.model_fields["tests"].default,
        coverage=ScribeConfig.model_fields["coverage"].default,
        conventions=ScribeConfig.model_fields["conventions"].default,
        cache=ScribeConfig.model_fields["cache"].default,
        version=1,
    )


def _model(name: str):
    manifest_node = next(
        node
        for node in parse_manifest(FIXTURE_PROJECT / "target" / "manifest.json")
        if node.name == name
    )
    return build_enriched_model(manifest_node, None, _config())


def test_generate_docs_returns_structured_result():
    provider = FakeProvider(
        """
        {
          "model_description": "Staged rugby fixtures.",
          "docs_block_content": "Long-form docs block.",
          "columns": {
            "league_id": "League identifier.",
            "home_score": "Home team score."
          }
        }
        """
    )

    result = generate_docs(_model("stg_api_sports__fixtures"), provider, _config())

    assert result == DocsResult(
        model_description="Staged rugby fixtures.",
        docs_block_content="Long-form docs block.",
        columns={
            "league_id": "League identifier.",
            "home_score": "Home team score.",
        },
    )
    system, user = provider.calls[0]
    assert "Return JSON only" in system
    assert "stg_api_sports__fixtures" in user
    assert "created_at" in user


def test_generate_docs_uses_mart_template_prompt():
    """Mart models use the four-section Python assembler (ADR-015).

    The LLM response feeds 'docs_block_content' (fallback path in
    _assemble_mart_docs_block). The assembler always opens with
    '# Description and Motivation' regardless of the LLM payload.
    """
    provider = FakeProvider(
        """
        {
          "model_description": "Rugby fixture mart.",
          "docs_block_content": "One row per fixture.",
          "columns": {}
        }
        """
    )

    model = _model("fixtures")
    result = generate_docs(model, provider, _config())

    assert model.layer is Layer.MARTS

    # The Python assembler always produces the four-section header first.
    assert result.docs_block_content.startswith("# Description and Motivation")

    # The LLM's docs_block_content value is used as the description body (fallback).
    assert "One row per fixture." in result.docs_block_content

    # All four section headers must be present.
    assert "# Known Limitations" in result.docs_block_content
    assert "# Business Stakeholder" in result.docs_block_content
    assert "# Technical Stakeholder" in result.docs_block_content

    # The mart-specific prompt template must have been used.
    assert "description_and_motivation" in provider.calls[0][1]


def test_generate_docs_raises_on_malformed_json():
    provider = FakeProvider("not json")

    with pytest.raises(ValueError, match="valid JSON"):
        generate_docs(_model("fixtures"), provider, _config())