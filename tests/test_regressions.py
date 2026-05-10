"""
Regression tests for bugs found and fixed during e2e validation.

Each test is named after the bug it covers and references the commit
fix/real-project-e2e-validation where the fix was implemented.

Bugs covered:
  R01 — manifest_parser: empty columns dict → sqlglot fallback
  R02 — manifest_parser: BigQuery backtick SQL parsed without dialect crash
  R03 — analyzer: multi-*_id model → no column typed as PK
  R04 — analyzer: fqn with 'mart/' (no s) → Layer.MARTS not Layer.UNKNOWN
  R05 — tests_generator: {test: not_null} format rejected by sanitizer
  R06 — tests_generator: StopIteration in _ensure_primary_key_tests (empty model)
  R07 — tests_generator: dbt_utils tests stripped by sanitizer
  R08 — tests_generator: nullable timestamps do not get not_null
  R09 — docs_generator: markdown fences stripped from JSON response
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from dbt_scribe.analyzer import (
    ColumnType,
    Layer,
    build_enriched_model,
    detect_layer,
)
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.tests_generator import (
    _ensure_primary_key_tests,
    _parse_json_response,
    _sanitize_tests,
    generate_tests,
)
from dbt_scribe.parsers.manifest_parser import ManifestColumn, ManifestNode, parse_manifest

FIXTURE_MANIFEST = (
    Path(__file__).parent / "fixtures" / "dbt_project" / "target" / "manifest.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> ScribeConfig:
    """Return a ScribeConfig instance that bypasses API key validation."""
    return ScribeConfig.model_construct(
        llm=None,
        docs=ScribeConfig.model_fields["docs"].default,
        tests=ScribeConfig.model_fields["tests"].default,
        coverage=ScribeConfig.model_fields["coverage"].default,
        conventions=ScribeConfig.model_fields["conventions"].default,
        cache=ScribeConfig.model_fields["cache"].default,
        version=1,
    )


def _make_node(
    name: str,
    fqn: list[str],
    compiled_code: str,
    columns: dict,
    *,
    adapter_type: str | None = "duckdb",
    materialized: str = "view",
) -> ManifestNode:
    """Construct a minimal ManifestNode for regression testing."""
    return ManifestNode(
        unique_id=f"model.fixture_project.{name}",
        name=name,
        fqn=fqn,
        resource_type="model",
        compiled_code=compiled_code,
        columns=columns,
        depends_on_nodes=[],
        tags=[],
        materialized=materialized,
        path=f"staging/{name}.sql",
        adapter_type=adapter_type,
        config={"materialized": materialized, "tags": []},
    )


# ---------------------------------------------------------------------------
# R01 — manifest_parser: empty columns dict triggers sqlglot fallback
# ---------------------------------------------------------------------------

def test_r01_empty_columns_dict_falls_back_to_sqlglot():
    """When manifest columns is {}, columns must be extracted from compiled SQL."""
    nodes = parse_manifest(FIXTURE_MANIFEST)
    bq_node = next(n for n in nodes if n.name == "stg_bq__orders")

    # The manifest has an empty columns dict for this node
    assert bq_node.columns, (
        "Expected sqlglot fallback to populate columns from compiled SQL, got empty dict"
    )
    # Columns inferred from the backtick-quoted BigQuery SELECT
    assert "order_id" in bq_node.columns
    assert "customer_id" in bq_node.columns
    assert "order_status" in bq_node.columns
    assert "created_at" in bq_node.columns
    assert "delivered_at" in bq_node.columns


# ---------------------------------------------------------------------------
# R02 — manifest_parser: BigQuery backtick SQL does not crash sqlglot
# ---------------------------------------------------------------------------

def test_r02_bigquery_backtick_sql_parsed_without_error():
    """Backtick-quoted BigQuery SQL must be parsed without raising an exception."""
    nodes = parse_manifest(FIXTURE_MANIFEST)
    bq_node = next(n for n in nodes if n.name == "stg_bq__orders")

    # If R01 passes, R02 also passed — parsing did not raise. This test
    # makes the intent explicit and gives a clearer failure message.
    assert isinstance(bq_node.columns, dict)
    assert len(bq_node.columns) > 0, (
        "BigQuery backtick SQL should parse to at least one column without crashing"
    )


# ---------------------------------------------------------------------------
# R03 — analyzer: multi-*_id model must not produce any PRIMARY_KEY column
# ---------------------------------------------------------------------------

def test_r03_multi_id_model_has_no_primary_key():
    """When multiple *_id columns exist, none should be typed as PRIMARY_KEY."""
    config = _make_config()
    node = _make_node(
        name="stg_orders",
        fqn=["fixture_project", "staging", "stg_orders"],
        compiled_code="select order_id, customer_id, order_status from raw.orders",
        columns={
            "order_id": ManifestColumn(name="order_id", data_type="integer", description=""),
            "customer_id": ManifestColumn(name="customer_id", data_type="integer", description=""),
            "order_status": ManifestColumn(name="order_status", data_type="varchar", description=""),
        },
    )
    enriched = build_enriched_model(node, None, config)
    pk_columns = [
        col for col in enriched.columns.values()
        if col.column_type is ColumnType.PRIMARY_KEY
    ]
    assert pk_columns == [], (
        f"Expected no PKs in a multi-id model, got: {[c.name for c in pk_columns]}"
    )


def test_r03_single_id_model_has_exactly_one_primary_key():
    """When only one *_id column exists, it must be typed as PRIMARY_KEY."""
    config = _make_config()
    node = _make_node(
        name="stg_fixtures",
        fqn=["fixture_project", "staging", "stg_fixtures"],
        compiled_code="select fixture_id, fixture_status from raw.fixtures",
        columns={
            "fixture_id": ManifestColumn(name="fixture_id", data_type="integer", description=""),
            "fixture_status": ManifestColumn(name="fixture_status", data_type="varchar", description=""),
        },
    )
    enriched = build_enriched_model(node, None, config)
    pk_columns = [
        col for col in enriched.columns.values()
        if col.column_type is ColumnType.PRIMARY_KEY
    ]
    assert len(pk_columns) == 1
    assert pk_columns[0].name == "fixture_id"


# ---------------------------------------------------------------------------
# R04 — analyzer: 'mart/' folder (no s) resolves to Layer.MARTS
# ---------------------------------------------------------------------------

def test_r04_mart_folder_without_s_resolves_to_marts_layer():
    """fqn with 'mart' (no trailing s) must resolve to Layer.MARTS, not Layer.UNKNOWN."""
    config = _make_config()
    layer = detect_layer(["fixture_project", "mart", "rugby", "orders"], config.conventions)
    assert layer is Layer.MARTS, (
        f"Expected Layer.MARTS for fqn[1]='mart', got {layer}"
    )


def test_r04_marts_folder_with_s_also_resolves_correctly():
    """Sanity check: the canonical 'marts' spelling still resolves to Layer.MARTS."""
    config = _make_config()
    layer = detect_layer(["fixture_project", "marts", "rugby", "orders"], config.conventions)
    assert layer is Layer.MARTS


# ---------------------------------------------------------------------------
# R05 — tests_generator: {test: "not_null"} wrong-key format is rejected
# ---------------------------------------------------------------------------

def test_r05_sanitizer_rejects_wrong_key_format():
    """The old {test: 'not_null'} format must be filtered out by _sanitize_tests."""
    malformed = [
        {"test": "not_null"},           # wrong key — was generated before the fix
        {"test": "unique"},             # wrong key
        {"not_null": {"name": "x_not_null"}},  # correct — must be kept
    ]
    result = _sanitize_tests(malformed)
    assert len(result) == 1
    assert "not_null" in result[0]


def test_r05_sanitizer_rejects_bare_strings():
    """Bare string test entries (e.g. 'not_null') must be rejected."""
    malformed = [
        "not_null",
        "unique",
        {"not_null": {"name": "x_not_null"}},
    ]
    result = _sanitize_tests(malformed)
    assert len(result) == 1


def test_r05_sanitizer_keeps_all_valid_standard_types():
    """All four standard dbt test types in correct format must pass sanitization."""
    valid = [
        {"not_null": {"name": "m_col_not_null"}},
        {"unique": {"name": "m_col_unique"}},
        {"accepted_values": {"name": "m_col_av", "arguments": {"values": ["a", "b"]}}},
        {"relationships": {"name": "m_col_fk", "arguments": {"to": "ref('x')", "field": "id"}}},
    ]
    result = _sanitize_tests(valid)
    assert len(result) == 4


# ---------------------------------------------------------------------------
# R06 — tests_generator: _ensure_primary_key_tests does not crash on empty model
# ---------------------------------------------------------------------------

def test_r06_ensure_pk_tests_does_not_crash_on_model_with_no_pk():
    """_ensure_primary_key_tests must not raise StopIteration on a model with no PK."""
    config = _make_config()
    node = _make_node(
        name="stg_no_pk",
        fqn=["fixture_project", "staging", "stg_no_pk"],
        compiled_code="select order_status, created_at from raw.orders",
        columns={
            "order_status": ManifestColumn(name="order_status", data_type="varchar", description=""),
            "created_at": ManifestColumn(name="created_at", data_type="timestamp", description=""),
        },
    )
    enriched = build_enriched_model(node, None, config)
    columns: dict = {}

    # Must not raise
    _ensure_primary_key_tests(enriched, columns)
    # No PK column → columns dict untouched
    assert columns == {}


def test_r06_ensure_pk_tests_adds_not_null_and_unique_for_pk_column():
    """_ensure_primary_key_tests must add not_null + unique in canonical order."""
    config = _make_config()
    node = _make_node(
        name="stg_fixtures",
        fqn=["fixture_project", "staging", "stg_fixtures"],
        compiled_code="select fixture_id, fixture_status from raw.fixtures",
        columns={
            "fixture_id": ManifestColumn(name="fixture_id", data_type="integer", description=""),
            "fixture_status": ManifestColumn(name="fixture_status", data_type="varchar", description=""),
        },
    )
    enriched = build_enriched_model(node, None, config)
    columns: dict = {}
    _ensure_primary_key_tests(enriched, columns)

    assert "fixture_id" in columns
    tests = columns["fixture_id"]
    test_types = [list(t.keys())[0] for t in tests]
    assert test_types[0] == "not_null"
    assert test_types[1] == "unique"


# ---------------------------------------------------------------------------
# R07 — tests_generator: dbt_utils tests are stripped by sanitizer
# ---------------------------------------------------------------------------

def test_r07_sanitizer_rejects_dbt_utils_tests():
    """dbt_utils test types must be rejected even if structurally well-formed."""
    with_dbt_utils = [
        {"dbt_utils.expression_is_true": {"name": "x_expr_true"}},
        {"dbt_utils.not_empty_string": {"name": "x_not_empty"}},
        {"not_null": {"name": "x_not_null"}},  # valid — must survive
    ]
    result = _sanitize_tests(with_dbt_utils)
    assert len(result) == 1
    assert "not_null" in result[0]


# ---------------------------------------------------------------------------
# R08 — tests_generator: nullable timestamps must not receive not_null
# ---------------------------------------------------------------------------

def test_r08_nullable_timestamp_not_typed_for_not_null():
    """
    Columns like delivered_at and picked_up_at are logically nullable.
    The prompt instructs the LLM not to add not_null for them, and the
    generate_tests function must honour this when the LLM complies.

    This test verifies that a mocked LLM response that omits not_null for
    nullable timestamps passes through generate_tests unchanged (i.e. the
    deterministic post-processing does not add not_null to timestamps).
    """
    config = _make_config()
    node = _make_node(
        name="stg_deliveries",
        fqn=["fixture_project", "staging", "stg_deliveries"],
        compiled_code=(
            "select order_id, created_at, delivered_at, picked_up_at "
            "from raw.deliveries"
        ),
        columns={
            "order_id": ManifestColumn(name="order_id", data_type="integer", description=""),
            "created_at": ManifestColumn(name="created_at", data_type="timestamp", description=""),
            "delivered_at": ManifestColumn(name="delivered_at", data_type="timestamp", description=""),
            "picked_up_at": ManifestColumn(name="picked_up_at", data_type="timestamp", description=""),
        },
    )
    enriched = build_enriched_model(node, None, config)

    # Mock provider returns a well-formed response with no not_null on nullable timestamps
    mock_response_payload = {
        "columns": {
            "order_id": [
                {"not_null": {"name": "stg_deliveries_order_id_not_null"}},
                {"unique": {"name": "stg_deliveries_order_id_unique"}},
            ],
            "created_at": [
                {"not_null": {"name": "stg_deliveries_created_at_not_null"}},
            ],
            # delivered_at and picked_up_at intentionally omitted — nullable timestamps
        }
    }
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MagicMock(
        content=json.dumps(mock_response_payload)
    )

    result = generate_tests(enriched, mock_provider, config)

    # Nullable timestamps must have NO tests added by post-processing
    assert "delivered_at" not in result.columns or result.columns["delivered_at"] == []
    assert "picked_up_at" not in result.columns or result.columns["picked_up_at"] == []

    # created_at (always-populated) retains its not_null
    assert any("not_null" in t for t in result.columns.get("created_at", []))


# ---------------------------------------------------------------------------
# R09 — docs_generator / tests_generator: markdown fences stripped from JSON
# ---------------------------------------------------------------------------

def test_r09_json_parser_strips_markdown_fences():
    """JSON wrapped in ```json ... ``` fences must be parsed without error."""
    raw_with_fences = '```json\n{"columns": {"order_id": []}}\n```'
    parsed = _parse_json_response(raw_with_fences)
    assert parsed == {"columns": {"order_id": []}}


def test_r09_json_parser_handles_plain_json():
    """Plain JSON (no fences) must also parse correctly."""
    raw_plain = '{"columns": {"order_id": []}}'
    parsed = _parse_json_response(raw_plain)
    assert parsed == {"columns": {"order_id": []}}


def test_r09_json_parser_strips_generic_code_fences():
    """JSON wrapped in plain ``` fences (no language tag) must also parse."""
    raw_plain_fences = '```\n{"columns": {}}\n```'
    parsed = _parse_json_response(raw_plain_fences)
    assert parsed == {"columns": {}}