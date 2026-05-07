from pathlib import Path

from dbt_scribe.parsers.yaml_parser import (
    YamlColumn,
    YamlModel,
    is_description_set,
    parse_yaml,
)

FIXTURE_YAML = (
    Path(__file__).parent
    / "fixtures"
    / "dbt_project"
    / "models"
    / "staging"
    / "api_sports"
    / "stg_api_sports__fixtures.yml"
)


def test_parse_yaml_returns_none_for_missing_file(tmp_path):
    assert parse_yaml(tmp_path / "missing.yml") is None


def test_parse_yaml_extracts_model_description_and_columns():
    model = parse_yaml(FIXTURE_YAML)

    assert model == YamlModel(
        name="stg_api_sports__fixtures",
        description="Staged rugby fixtures from the API Sports source.",
        columns={
            "fixture_id": YamlColumn(
                name="fixture_id",
                description="{{ doc('fixture_id') }}",
                tests=["not_null", "unique"],
            ),
            "league_id": YamlColumn(name="league_id", description="", tests=[]),
            "home_team_id": YamlColumn(name="home_team_id", description="", tests=[]),
            "away_team_id": YamlColumn(name="away_team_id", description="", tests=[]),
            "fixture_status": YamlColumn(
                name="fixture_status",
                description="Current status of the fixture (e.g. NS, FT, CANC).",
                tests=[],
            ),
            "fixture_date": YamlColumn(name="fixture_date", description="", tests=[]),
            "home_score": YamlColumn(name="home_score", description="", tests=[]),
            "away_score": YamlColumn(name="away_score", description="", tests=[]),
            "is_finished": YamlColumn(name="is_finished", description="", tests=[]),
            "created_at": YamlColumn(
                name="created_at",
                description="{{ doc('created_at') }}",
                tests=[],
            ),
            "updated_at": YamlColumn(
                name="updated_at",
                description="{{ doc('updated_at') }}",
                tests=[],
            ),
        },
    )


def test_is_description_set_false_for_missing_or_empty_text():
    assert is_description_set(None) is False
    assert is_description_set("") is False
    assert is_description_set("   ") is False


def test_is_description_set_true_for_inline_text():
    assert is_description_set("Current status of the fixture.") is True


def test_is_description_set_true_for_doc_reference():
    assert is_description_set("{{ doc('fixture_id') }}") is True
    assert is_description_set('{{ doc("fixture_id") }}') is True
