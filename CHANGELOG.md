# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Added a self-contained catalog HTML reporter backed by a packaged Jinja2 template.
- Added HTML reporter tests covering file creation, automatic parent directory
  creation, expected coverage content, semantic markup, and absence of external
  assets.
- Added wheel build configuration for the `dbt_scribe` package so templates are
  included in built distributions.
- Added a CDC §4.2 catalog JSON reporter with report metadata, thresholds, a global
  score block, keyed layer aggregates, model details, and missing-column arrays.
- Added JSON reporter tests for parseability, required top-level keys, ISO 8601
  UTC `Z` timestamps, model count, missing-column lists, keyed layers, and threshold
  pass/fail status.

## [0.1.1] — 2026-05-10

### Fixed

- Default Anthropic model updated to `claude-sonnet-4-6` (4.x generation, no date suffix)
- Added `default_contact` field to `DocsConfig`
- Regression tests for all bugs fixed during e2e validation

[0.1.1]: https://github.com/jeremy6680/dbt-scribe/compare/v0.1.0...v0.1.1

## [0.1.0] — 2026-05-10

Initial public release.

### Added

- `dbt-scribe init` — generates a `dbt-scribe.yml` config at the dbt project root
- `dbt-scribe docs` — LLM-powered model and column description generation
- `dbt-scribe tests` — LLM-powered generic test generation (not_null, unique,
  accepted_values, relationships) with deterministic PK/enum safeguards
- `dbt-scribe generate` — runs docs + tests in a single command
- `dbt-scribe audit` — reports documentation and test coverage per model
- Multi-provider support: Anthropic Claude, OpenAI, Google Gemini
- Two-tier documentation: short inline YAML descriptions + long `*__docs.md` docs blocks
- Four-section mart template (Description, Limitations, Business Stakeholder,
  Technical Stakeholder) assembled deterministically in Python
- Non-destructive YAML writer: creates from scratch or merges without overwriting
  existing descriptions (unless `--force` is passed)
- `{{ doc("...") }}` references treated as filled — never overwritten
- Layer detection from `fqn` with alternate-spelling fallbacks (mart/marts, stg/staging)
- Column type inference cascade: PK → FK → enum → shared → boolean → timestamp →
  metric → calculated → text
- Single-PK heuristic: only designates a column as PRIMARY_KEY when exactly one
  `*_id` column exists in the model
- sqlglot fallback for column extraction when manifest `columns` dict is empty
  (no YAML existed at compile time), with multi-dialect cascade for BigQuery
  backtick quoting
- Structured JSON-only LLM responses with markdown fence stripping
- dbt_utils test sanitizer — only standard dbt generic test types are written
- Named tests throughout (dbt >= 1.10.5 syntax with `arguments:` key)
- Nullable timestamp protection — columns like `delivered_at`/`picked_up_at`
  never receive `not_null` automatically
- GitHub Actions CI: ruff + mypy + pytest on every push and PR
- Fixture-based test suite — no dbt installation, warehouse, or API keys required

### Configuration

- `dbt-scribe.yml` with Pydantic v2 validation
- `DocsConfig.default_contact` field for mart stakeholder sections
- Default LLM model: `claude-sonnet-4-6` (Anthropic 4.x generation, no date suffix)

[0.1.0]: https://github.com/jeremy6680/dbt-scribe/releases/tag/v0.1.0
