from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

if TYPE_CHECKING:
    from dbt_scribe.generators.base_generator import LLMProvider


class ConfigError(Exception):
    pass


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "anthropic"
    model: str | None = None
    temperature: float = 0.2

    @field_validator("provider")
    @classmethod
    def provider_must_be_valid(cls, v: str) -> str:
        valid = {"anthropic", "openai", "google"}
        if v not in valid:
            raise ValueError(f"provider must be one of {valid}, got {v!r}")
        return v

    @property
    def resolved_model(self) -> str:
        if self.model:
            return self.model
        defaults = {
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "google": "gemini-2.5-pro",
        }
        return defaults[self.provider]

    @property
    def api_key_env_var(self) -> str:
        return {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
        }[self.provider]


class DocsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    two_tier: bool = True
    shared_columns: list[str] = ["created_at", "updated_at", "_fivetran_synced"]
    default_owner: str = "Data Team"


class TestsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pk_patterns: list[str] = ["^.*_id$", "^id$"]
    fk_patterns: list[str] = ["^.*_fk$"]
    enum_patterns: list[str] = ["^.*_type$", "^.*_status$", "^.*_category$"]


class CoverageConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_doc_coverage: int = 80
    min_test_coverage: int = 70


class ConventionsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    staging_prefix: str = "staging"
    intermediate_prefix: str = "intermediate"
    marts_prefix: str = "marts"


class CacheConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    directory: str = ".dbt-scribe-cache"


class ScribeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    llm: LLMConfig = LLMConfig()
    docs: DocsConfig = DocsConfig()
    tests: TestsConfig = TestsConfig()
    coverage: CoverageConfig = CoverageConfig()
    conventions: ConventionsConfig = ConventionsConfig()
    cache: CacheConfig = CacheConfig()
    model_root: str = "models"

    @model_validator(mode="after")
    def check_api_key_present(self) -> ScribeConfig:
        env_var = self.llm.api_key_env_var
        if not os.environ.get(env_var):
            raise ConfigError(
                f"Missing API key: set the {env_var} environment variable "
                f"for provider {self.llm.provider!r}."
            )
        return self


def load_config(path: Path | str, *, check_api_key: bool = True, model_root: str = "models") -> ScribeConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            "Run 'dbt-scribe init' to generate a default dbt-scribe.yml."
        )
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a YAML mapping, got {type(raw).__name__}")

    try:
        if check_api_key:
            config = ScribeConfig(**raw)
        else:
            # Skip API key validation during bootstrap / init
            config = ScribeConfig.model_construct()
            config.llm = LLMConfig(**raw.get("llm", {}))
            config.docs = DocsConfig(**raw.get("docs", {}))
            config.tests = TestsConfig(**raw.get("tests", {}))
            config.coverage = CoverageConfig(**raw.get("coverage", {}))
            config.conventions = ConventionsConfig(**raw.get("conventions", {}))
            config.cache = CacheConfig(**raw.get("cache", {}))
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"Invalid configuration in {path}: {exc}") from exc
    return config.model_copy(update={"model_root": model_root})


def resolve_provider(config: ScribeConfig) -> LLMProvider:
    from dbt_scribe.generators.providers.anthropic_provider import AnthropicProvider
    from dbt_scribe.generators.providers.google_provider import GoogleProvider
    from dbt_scribe.generators.providers.openai_provider import OpenAIProvider

    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "google": GoogleProvider,
    }
    cls = providers[config.llm.provider]
    return cls(model=config.llm.resolved_model, temperature=config.llm.temperature)  # type: ignore[abstract]
