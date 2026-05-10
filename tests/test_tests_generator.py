# tests/test_tests_generator.py
from pathlib import Path

import pytest

from dbt_scribe.analyzer import (
    ColumnType,
    EnrichedColumn,
    EnrichedModel,
    Layer,
    build_enriched_model,
)
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.base_generator import LLMResponse
from dbt_scribe.generators.tests_generator import generate_tests
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


def _model_from_manifest(name: str) -> EnrichedModel:
    """Build a model from the fixture manifest via build_enriched_model."""
    manifest_node = next(
        node
        for node in parse_manifest(FIXTURE_PROJECT / "target" / "manifest.json")
        if node.name == name
    )
    return build_enriched_model(manifest_node, None, _config())


def _model_with_pk() -> EnrichedModel:
    """Build a minimal EnrichedModel with an unambiguous PRIMARY_KEY column.

    All fixture manifest models have multiple *_id columns, so _find_primary_key_column
    never returns a sole PK candidate. This helper constructs a model directly so that
    tests for _ensure_primary_key_tests and _ensure_enum_placeholders remain focused
    on generator behaviour rather than on manifest structure.
    """
    pk_col = EnrichedColumn(
        name="fixture_id",
        data_type="integer",
        description=None,
        tests=[],
        column_type=ColumnType.PRIMARY_KEY,
        sql_expression="fixture_id",
        needs_doc=True,
        needs_tests=True,
    )
    enum_col = EnrichedColumn(
        name="fixture_status",
        data_type="varchar",
        description=None,
        tests=[],
        column_type=ColumnType.ENUM,
        sql_expression="fixture_status",
        needs_doc=True,
        needs_tests=True,
    )
    return EnrichedModel(
        unique_id="model.fixture_project.fixtures",
        name="fixtures",
        fqn=["fixture_project", "marts", "rugby", "fixtures"],
        layer=Layer.MARTS,
        description=None,
        compiled_code="select fixture_id, fixture_status from final",
        columns={"fixture_id": pk_col, "fixture_status": enum_col},
        depends_on_nodes=[],
        tags=[],
        materialized="table",
        path="marts/rugby/fixtures.sql",
        adapter_type="duckdb",
    )


def test_generate_tests_returns_structured_result_and_preserves_named_tests():
    """LLM output for enum columns is preserved; PK safeguard appends missing tests."""
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

    result = generate_tests(_model_from_manifest("stg_api_sports__fixtures"), provider, _config())

    # The LLM-supplied enum test is preserved as-is (already valid format).
    assert result.columns["fixture_status"] == [
        {
            "accepted_values": {
                "name": "accepted_values_stg_api_sports__fixtures_fixture_status",
                "values": ["NS", "FT"],
            }
        }
    ]
    # The enum column name must appear in the prompt sent to the LLM.
    assert "fixture_status" in provider.calls[0][1]


def test_generate_tests_pk_always_gets_unique_and_not_null():
    """_ensure_primary_key_tests always injects not_null + unique for PK columns.

    Uses _model_with_pk() because all fixture manifest models have multiple *_id
    columns, preventing unambiguous PK detection via build_enriched_model alone.
    """
    provider = FakeProvider('{"columns": {}}')

    result = generate_tests(_model_with_pk(), provider, _config())

    assert result.columns["fixture_id"] == [
        {"not_null": {"name": "fixtures_fixture_id_not_null"}},
        {"unique": {"name": "fixtures_fixture_id_unique"}},
    ]


def test_generate_tests_adds_placeholder_accepted_values_for_enum():
    """_ensure_enum_placeholders injects an accepted_values entry with dbt 1.10.5+ format.

    The placeholder uses the 'arguments' key (not 'values' directly) and includes a
    'todo' annotation for the engineer to fill in real values.

    Uses _model_with_pk() for the same reason as test_generate_tests_pk_always_gets_unique_and_not_null.
    """
    provider = FakeProvider('{"columns": {}}')

    result = generate_tests(_model_with_pk(), provider, _config())

    assert result.columns["fixture_status"] == [
        {
            "accepted_values": {
                "name": "fixtures_fixture_status_accepted_values",
                "arguments": {"values": []},
                "todo": "fill with actual enum values from source system",
            }
        }
    ]


def test_generate_tests_raises_on_malformed_json():
    provider = FakeProvider("not json")

    with pytest.raises(ValueError, match="valid JSON"):
        generate_tests(_model_from_manifest("stg_api_sports__fixtures"), provider, _config())