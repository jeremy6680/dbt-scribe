# NEXT_STEPS.md — dbt-scribe

## Current phase: Phase 1 — Working MVP complete

**Goal:** End-to-end generation on a single model using the manifest, with the
`docs`, `tests`, and `generate` commands. Tested against a real dbt project.

**Test project:** `/Users/jeremymarchandeau/Code/personal/learning/databird-dbt-exercices/exercice_bonus_module_3/`

**Status:** The code-complete MVP is implemented and covered by fixture-based tests
that do not require dbt, a warehouse, or live LLM calls. One manual validation item
remains before calling the project release-ready: run the tool against the external
dbt exercise project in an environment where `dbt` is installed and the project has
its own `dbt-scribe.yml`.

---

## Steps

### Step 01 — Project scaffolding `step/01-scaffolding` ✅

- [x] `pyproject.toml` — packaging, dependencies, CLI entry point (`dbt-scribe`)
- [x] `dbt_scribe/__init__.py`
- [x] Empty module stubs for all packages (parsers, generators, writers)
- [x] `.env.example`
- [x] `.gitignore` (add `.dbt-scribe-cache/`, `.env`, `*.duckdb`, `dist/`, `__pycache__/`)
- [x] `tests/conftest.py` (empty)
- [x] `tests/fixtures/dbt_project/` — minimal dbt project with pre-generated `manifest.json`
- [x] Verify `pip install -e .` works and `dbt-scribe --help` is reachable

---

### Step 02 — Config + Bootstrap `step/02-config-bootstrap` ✅

- [x] `dbt_scribe/config.py`
  - Pydantic models: `LLMConfig`, `DocsConfig`, `TestsConfig`,
    `CoverageConfig`, `ConventionsConfig`, `CacheConfig`, `ScribeConfig`
  - `load_config(path) -> ScribeConfig`
  - `resolve_provider(config) -> LLMProvider`
- [x] `dbt_scribe/cli.py`
  - Click group `dbt-scribe`
  - Bootstrap check `_bootstrap(cwd)` raises `BootstrapError` if any of the three
    required files are missing; all commands except `init` call it
  - Skeleton commands: `docs`, `tests`, `generate`, `audit` (each raises ClickException)
  - `init` command — writes default `dbt-scribe.yml` template
- [x] `tests/test_config.py` — 18 tests: valid config loads, missing keys use defaults,
      bad provider raises `ConfigError`, missing API key raises `ConfigError`,
      `resolve_provider` returns the correct class for all three providers
- [x] `tests/test_bootstrap.py` — 7 tests: correct CWD passes, each missing file raises
      `BootstrapError` with a contextual hint, all-missing lists all three

**Also completed as part of Step 02** (originally planned for Step 06):
- [x] `dbt_scribe/generators/base_generator.py` — `LLMProvider` ABC + `LLMResponse`
      dataclass + 3-attempt exponential backoff retry in `complete()`
- [x] `dbt_scribe/generators/providers/anthropic_provider.py` — full implementation
- [x] `dbt_scribe/generators/providers/openai_provider.py` — full implementation
- [x] `dbt_scribe/generators/providers/google_provider.py` — full implementation
      (uses `google-genai` SDK, not the deprecated `google-generativeai`)

---

### Step 03 — Manifest parser `step/03-manifest-parser` ✅

- [x] `dbt_scribe/parsers/manifest_parser.py`
  - `parse_manifest(manifest_path) -> list[ManifestNode]`
  - Extracts per node: `unique_id`, `name`, `fqn`, `resource_type`, `compiled_code`,
    `columns` (name + data_type + description), `depends_on.nodes`, `config` (tags,
    materialized), `path`, adapter type from `metadata.adapter_type`
  - `ManifestNode` and `ManifestColumn` dataclasses
  - Filters to `resource_type == "model"` only
- [x] `tests/test_manifest_parser.py` — parse fixture manifest, verify node count,
      verify compiled SQL is present, verify columns extracted, verify fqn

**Validation:** 29 pytest tests passing. Manifest parser tests use only
`tests/fixtures/dbt_project/target/manifest.json`; no dbt or warehouse dependency.

---

### Step 04 — YAML parser `step/04-yaml-parser` ✅

- [x] `dbt_scribe/parsers/yaml_parser.py`
  - `parse_yaml(yaml_path) -> YamlModel | None` (returns None if file does not exist)
  - `YamlModel` dataclass: model name, description, columns dict
  - `YamlColumn` dataclass: name, description, tests list
  - `is_description_set(description: str | None) -> bool`
    — returns True if non-empty string OR contains `{{ doc("...") }}`
- [x] `tests/test_yaml_parser.py` — empty description → False, inline text → True,
      `{{ doc("...") }}` reference → True, missing file → None

**Validation:** 34 pytest tests passing. YAML parser tests use the checked-in
fixture YAML and do not require dbt or a warehouse.

---

### Step 05 — Analyzer `step/05-analyzer` ✅

- [x] `dbt_scribe/analyzer.py`
  - `detect_layer(fqn: list[str], config: ConventionsConfig) -> Layer`
    — uses fqn[1] path prefix matching against configured layer prefixes
  - `infer_column_type(column_name: str, sql_expression: str | None, config: TestsConfig) -> ColumnType`
    — applies pk/fk/enum/shared patterns from config; falls back to heuristics
    (boolean prefixes `is_`/`has_`/`did_`, timestamp suffixes `_at`/`_date`,
    metric/calculated if sql_expression is non-null and contains aggregation or arithmetic)
  - `build_enriched_model(node: ManifestNode, yaml_model: YamlModel | None, config: ScribeConfig) -> EnrichedModel`
  - `EnrichedModel`, `EnrichedColumn`, `Layer`, and `ColumnType`
- [x] `tests/test_analyzer.py` — layer detection from fqn, all ColumnType variants,
      `needs_doc` / `needs_tests` flags respect `overwrite_existing`

**Validation:** 38 pytest tests passing. Analyzer tests use only checked-in
manifest/YAML fixtures and do not require dbt or a warehouse.

---

### Step 06 — LLM providers `step/06-llm-providers` ✅

- [x] `dbt_scribe/generators/base_generator.py` — completed in Step 02
- [x] `dbt_scribe/generators/providers/anthropic_provider.py` — completed in Step 02
- [x] `dbt_scribe/generators/providers/openai_provider.py` — completed in Step 02
- [x] `dbt_scribe/generators/providers/google_provider.py` — completed in Step 02
- [x] Retry logic (3 attempts, exponential backoff) in `LLMProvider.complete()` — completed in Step 02
- [x] `tests/test_providers.py` — all three providers tested with mocked HTTP responses;
      verify `LLMResponse` is normalized identically regardless of provider

**Validation:** 41 pytest tests passing. Provider tests mock SDK clients directly
and do not make network calls.

---

### Step 07 — Generators + prompts `step/07-generators` ✅

- [x] `dbt_scribe/prompts/docs_staging.j2`
- [x] `dbt_scribe/prompts/docs_intermediate.j2`
- [x] `dbt_scribe/prompts/docs_mart.j2`
- [x] `dbt_scribe/prompts/tests_generic.j2`
- [x] `dbt_scribe/generators/docs_generator.py`
  - `generate_docs(model: EnrichedModel, provider: LLMProvider, config: ScribeConfig) -> DocsResult`
  - `DocsResult` dataclass: model_description, docs_block_content, columns dict
- [x] `dbt_scribe/generators/tests_generator.py`
  - `generate_tests(model: EnrichedModel, provider: LLMProvider, config: ScribeConfig) -> TestsResult`
  - `TestsResult` dataclass: columns dict with test lists
- [x] JSON response parsing + validation (raise on malformed JSON)
- [x] `tests/test_docs_generator.py` — mocked provider, verify output structure,
      verify mart template is applied, verify shared columns are handled
- [x] `tests/test_tests_generator.py` — mocked provider, verify named tests, verify
      PK always gets unique+not_null, verify placeholder accepted_values

**Validation:** 48 pytest tests passing. Generator tests use mocked providers and
do not make network calls.

---

### Step 08 — Writers `step/08-writers` ✅

- [x] `dbt_scribe/writers/yaml_writer.py`
  - `write_yaml(model: EnrichedModel, docs_result: DocsResult, tests_result: TestsResult, config: ScribeConfig, dry_run: bool) -> WriterResult`
  - Mode detection: create from scratch if no `.yml` exists, merge otherwise
  - Creation: canonical structure (ordered sections, section comments, persist_docs
    conditional on layer, tags from fqn)
  - Merge: non-destructive (respect `is_description_set`, never delete existing tests)
  - `--force` flag bypasses `is_description_set` guard
- [x] `dbt_scribe/writers/docs_writer.py`
  - `write_docs_block(model: EnrichedModel, docs_result: DocsResult, config: ScribeConfig, dry_run: bool) -> WriterResult`
  - Appends new `{% docs %}` blocks to the correct `*__docs.md` file
  - Creates the file if it does not exist
  - Does not duplicate blocks that already exist (checks by block name)
- [x] `tests/test_yaml_writer.py` — create from scratch (verify structure), merge
      without force (existing descriptions preserved), merge with force (descriptions
      overwritten), existing tests never deleted, `doc()` refs preserved
- [x] `tests/test_docs_writer.py` — new file created, existing file appended,
      duplicate block not written twice

**Validation:** 56 pytest tests passing. Writer tests operate on copied fixture
projects and do not require dbt or a warehouse.

---

### Step 09 — Wire up CLI commands `step/09-cli-commands` ✅

- [x] `dbt-scribe docs --target <path>` — full pipeline: resolve → parse → analyze →
      generate docs → write YAML + docs.md
- [x] `dbt-scribe tests --target <path>` — full pipeline: → generate tests → write YAML
- [x] `dbt-scribe generate --target <path>` — docs + tests in one pass
- [x] `dbt-scribe audit --target <path>` — coverage report (table format), no generation
- [x] Resolver: file / directory / project root
- [x] `--dry-run` works across all commands
- [x] `--force` works across all commands
- [x] Rich output: per-model status lines, summary table

**Validation:** 66 pytest tests passing. CLI tests use copied fixture projects and
mocked providers/generators; no dbt, warehouse, or LLM calls are required.

---

### Step 10 — End-to-end test + CI `step/10-e2e-ci`

- [ ] End-to-end test on `databird-dbt-exercices/exercice_bonus_module_3/`
  - Run `dbt compile` in the test project first
  - Run `dbt-scribe generate --target models/ --dry-run`
  - Verify output is valid YAML and valid dbt syntax
- [x] `tests/` — integration test using the fixture dbt project + fixture manifest
- [x] `.github/workflows/ci.yml` — ruff + mypy + pytest on push/PR
- [x] CI status badge in README

**Validation:** 67 pytest tests passing and `ruff check .` passing. The external
dbt project end-to-end run was not completed in this environment because `dbt` was
not available and the external project did not yet contain `dbt-scribe.yml`.

---

### Post-MVP bugfix session `2026-05-08`

Eight issues identified by code review and fixed before first real-project use:

- `yaml_writer.py` — `WriterResult.changed` was always `True`; now compares serialised
  content before and after merge (dry-run output is now reliable)
- `config.py` / `cli.py` — `ConfigError` raised by the Pydantic `model_validator`
  (missing API key) escaped all `except` blocks and caused an unhandled crash; now
  caught in `_load_project`
- `cli.py` / `yaml_writer.py` / `docs_writer.py` / `resolver.py` — `"models/"` prefix
  was hardcoded; `model_root` is now read from `dbt_project.yml#model-paths` (see ADR-012)
- `yaml_writer.py` — `tests → data_tests` key migration only ran when new tests were
  added; now runs unconditionally for every column touched, producing consistent YAML
- `base_generator.py` — retry loop caught all exceptions including non-retryable 4xx
  errors; non-retryable status codes are now re-raised immediately (see ADR-013)
- `tests_generator.py` — `[not_null, unique]` PK test order was wrong when only one of
  the two was missing; rewritten to reconstruct the list in canonical order
- `resolver.py` — redundant third `_is_relative_to` condition removed
- `.github/workflows/ci.yml` — `mypy dbt_scribe` step was documented but absent; added

---

## Backlog (Phase 2+)

- `ruamel.yaml` migration (currently using `PyYAML` for Phase 1 simplicity)
- Singular test generation (marts)
- Cache LLM (SHA-256 compiled_sql + config_fingerprint)
- `--format json | markdown` for audit
- Manifest staleness warning
- PyPI publication
