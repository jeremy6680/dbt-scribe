from pathlib import Path

import pytest

from dbt_scribe.analyzer import build_enriched_model
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.base_generator import LLMResponse
from dbt_scribe.generators.tests_generator import generate_tests
from dbt_scribe.parsers.manifest_parser import parse_manifest

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

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


def test_generate_tests_returns_structured_result_and_preserves_named_tests():
    provider = FakeProvider(
        """
        {
          "columns": {
            "fixture_status": [
              {
                "accepted_values": {
                  "name": "accepted_values_stg_api_sports__fixtures_fixture_status",
                  "values": ["NS", "FT"]
                }
              }
            ]
          }
        }
        """
    )

    result = generate_tests(_model("stg_api_sports__fixtures"), provider, _config())

    assert result.columns["fixture_status"] == [
        {
            "accepted_values": {
                "name": "accepted_values_stg_api_sports__fixtures_fixture_status",
                "values": ["NS", "FT"],
            }
        }
    ]
    assert result.columns["fixture_id"] == [
        {"not_null": {"name": "not_null_stg_api_sports__fixtures_fixture_id"}},
        {"unique": {"name": "unique_stg_api_sports__fixtures_fixture_id"}},
    ]
    assert "fixture_status" in provider.calls[0][1]


def test_generate_tests_pk_always_gets_unique_and_not_null():
    provider = FakeProvider('{"columns": {}}')

    result = generate_tests(_model("fixtures"), provider, _config())

    assert result.columns["fixture_id"] == [
        {"not_null": {"name": "not_null_fixtures_fixture_id"}},
        {"unique": {"name": "unique_fixtures_fixture_id"}},
    ]


def test_generate_tests_adds_placeholder_accepted_values_for_enum():
    provider = FakeProvider('{"columns": {}}')

    result = generate_tests(_model("fixtures"), provider, _config())

    assert result.columns["fixture_status"] == [
        {
            "accepted_values": {
                "name": "accepted_values_fixtures_fixture_status",
                "values": [],
            }
        }
    ]


def test_generate_tests_raises_on_malformed_json():
    provider = FakeProvider("not json")

    with pytest.raises(ValueError, match="valid JSON"):
        generate_tests(_model("fixtures"), provider, _config())
