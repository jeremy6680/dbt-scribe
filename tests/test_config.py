from pathlib import Path

import pytest

from dbt_scribe.config import (
    CacheConfig,
    ConfigError,
    ConventionsConfig,
    CoverageConfig,
    DocsConfig,
    LLMConfig,
    ScribeConfig,
    TestsConfig,
    load_config,
    resolve_provider,
)

FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "dbt_project" / "dbt-scribe.yml"


# ── LLMConfig ────────────────────────────────────────────────────────────────


def test_llm_config_defaults():
    cfg = LLMConfig()
    assert cfg.provider == "anthropic"
    assert cfg.temperature == 0.2
    # claude-sonnet-4-6 is the current 4.x generation model (no date suffix)
    assert cfg.resolved_model == "claude-sonnet-4-6"


def test_llm_config_resolved_model_explicit():
    cfg = LLMConfig(provider="openai", model="gpt-4o-mini")
    assert cfg.resolved_model == "gpt-4o-mini"


def test_llm_config_resolved_model_defaults_per_provider():
    assert LLMConfig(provider="openai").resolved_model == "gpt-4o"
    assert LLMConfig(provider="google").resolved_model == "gemini-2.5-pro"


def test_llm_config_invalid_provider():
    with pytest.raises(ValueError, match="provider must be one of"):
        LLMConfig(provider="cohere")


def test_llm_config_api_key_env_var():
    assert LLMConfig(provider="anthropic").api_key_env_var == "ANTHROPIC_API_KEY"
    assert LLMConfig(provider="openai").api_key_env_var == "OPENAI_API_KEY"
    assert LLMConfig(provider="google").api_key_env_var == "GOOGLE_API_KEY"


# ── DocsConfig ───────────────────────────────────────────────────────────────


def test_docs_config_defaults():
    cfg = DocsConfig()
    assert cfg.two_tier is True
    assert "created_at" in cfg.shared_columns
    assert cfg.default_owner == "Data Team"
    # default_contact must exist and default to empty string (referenced in CDC)
    assert cfg.default_contact == ""


def test_docs_config_default_contact_settable():
    cfg = DocsConfig(default_contact="data@example.com")
    assert cfg.default_contact == "data@example.com"


# ── ScribeConfig defaults ────────────────────────────────────────────────────


def test_scribe_config_all_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg = ScribeConfig()
    assert cfg.version == 1
    assert isinstance(cfg.llm, LLMConfig)
    assert isinstance(cfg.docs, DocsConfig)
    assert isinstance(cfg.tests, TestsConfig)
    assert isinstance(cfg.coverage, CoverageConfig)
    assert isinstance(cfg.conventions, ConventionsConfig)
    assert isinstance(cfg.cache, CacheConfig)


def test_scribe_config_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        ScribeConfig()


def test_scribe_config_missing_api_key_wrong_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        ScribeConfig(llm=LLMConfig(provider="openai"))


# ── load_config ──────────────────────────────────────────────────────────────


def test_load_config_fixture(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.llm.provider == "anthropic"
    assert cfg.docs.two_tier is True
    assert "created_at" in cfg.docs.shared_columns
    assert cfg.tests.pk_patterns == ["^.*_id$", "^id$"]
    assert cfg.coverage.min_doc_coverage == 80


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("/nonexistent/dbt-scribe.yml"))


def test_load_config_invalid_yaml(tmp_path):
    bad = tmp_path / "dbt-scribe.yml"
    bad.write_text("{\ninvalid: yaml: [")
    with pytest.raises(ConfigError, match="Failed to parse"):
        load_config(bad)


def test_load_config_not_a_mapping(tmp_path):
    bad = tmp_path / "dbt-scribe.yml"
    bad.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(bad)


def test_load_config_bad_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    bad = tmp_path / "dbt-scribe.yml"
    bad.write_text("version: 1\nllm:\n  provider: cohere\n")
    with pytest.raises(ConfigError, match="Invalid configuration"):
        load_config(bad)


def test_load_config_unknown_keys_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg_file = tmp_path / "dbt-scribe.yml"
    cfg_file.write_text("version: 1\nfuture_key: some_value\n")
    cfg = load_config(cfg_file)
    assert cfg.version == 1


def test_load_config_no_api_key_check(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg_file = tmp_path / "dbt-scribe.yml"
    cfg_file.write_text("version: 1\n")
    cfg = load_config(cfg_file, check_api_key=False)
    assert cfg.llm.provider == "anthropic"


# ── resolve_provider ─────────────────────────────────────────────────────────


def test_resolve_provider_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg = ScribeConfig()
    provider = resolve_provider(cfg)
    from dbt_scribe.generators.providers.anthropic_provider import AnthropicProvider
    assert isinstance(provider, AnthropicProvider)


def test_resolve_provider_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = ScribeConfig(llm=LLMConfig(provider="openai"))
    provider = resolve_provider(cfg)
    from dbt_scribe.generators.providers.openai_provider import OpenAIProvider
    assert isinstance(provider, OpenAIProvider)


def test_resolve_provider_google(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    cfg = ScribeConfig(llm=LLMConfig(provider="google"))
    provider = resolve_provider(cfg)
    from dbt_scribe.generators.providers.google_provider import GoogleProvider
    assert isinstance(provider, GoogleProvider)