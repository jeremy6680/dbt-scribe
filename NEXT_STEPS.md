# NEXT_STEPS.md — dbt-scribe

## Current phase: Phase 2 — v0.2.0 `dbt-scribe catalog`

**Published package:** [`dbt-scribe` on PyPI](https://pypi.org/project/dbt-scribe/)
**Latest stable version:** `0.1.1`
**In development:** `0.2.0`
**Test project:** `/Users/jeremymarchandeau/Code/personal/learning/databird-dbt-exercices/exercice_bonus_module_3/`
**`catalog.json` confirmed:** ✅ available at `target/catalog.json`

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

### Step 10 — End-to-end test + CI `step/10-e2e-ci` ✅

- [x] End-to-end test on `databird-dbt-exercices/exercice_bonus_module_3/dbt-test-1/`
  - Real BigQuery project, 13 models across staging / intermediate / mart layers
  - `dbt-scribe generate --target models/` — all 13 models generated successfully
  - 100% doc coverage across all models
  - Named tests generated with correct dbt 1.10.5+ syntax
  - Four-section mart docs block correctly assembled
- [x] `tests/` — integration test using the fixture dbt project + fixture manifest
- [x] `.github/workflows/ci.yml` — ruff + mypy + pytest on push/PR
- [x] CI status badge in README

**Bugs found and fixed during e2e validation (committed on `fix/real-project-e2e-validation`):**

- `manifest_parser`: empty `columns` dict when no YAML exists at compile time →
  sqlglot fallback with multi-dialect cascade (ADR-014)
- `manifest_parser`: BigQuery backtick quoting rejected by sqlglot without dialect hint
- `analyzer`: all `*_id` columns typed as PK — fixed to only designate PK when a single
  `*_id` column exists in the model
- `analyzer`: `Layer.UNKNOWN` on `mart/` folder (vs configured `marts/`) — fixed with
  alternate spelling fallbacks (ADR-016)
- `docs_generator`: four-section mart template ignored by LLM — fixed by assembling
  structure in Python (ADR-015)
- `docs_generator`: markdown fences in LLM JSON responses causing parse errors
- `tests_generator`: wrong test format (`{test: not_null}`) — fixed with sanitizer +
  correct dbt 1.10.5+ `arguments:` format
- `tests_generator`: `StopIteration` crash in `_ensure_primary_key_tests`
- `tests_generator`: `dbt_utils` tests generated despite not being requested
- Nullable timestamps (`delivered_at`, `picked_up_at`) incorrectly getting `not_null`
- Environment setup: `ANTHROPIC_API_KEY` must be in `~/.zprofile` on Mac, not `~/.zshrc`

---

### Step 11 — Pre-publication fixes + PyPI publish ✅

- [x] Default Anthropic model updated to `claude-sonnet-4-6` (4.x generation, no date suffix)
      — `dbt-scribe.yml` init template + `config.py` default + fixture YAML + README
- [x] `DocsConfig.default_contact` field added (referenced in CDC, missing from implementation)
- [x] Regression tests written for all 9 bugs fixed during e2e validation (`tests/test_regressions.py`)
- [x] BigQuery fixture node added to `tests/fixtures/dbt_project/target/manifest.json`
      (`stg_bq__orders` — empty `columns` dict + backtick SQL) — covers ADR-014 in CI
- [x] `CHANGELOG.md` created
- [x] Published to PyPI as `v0.1.0`, then `v0.1.1`
- [x] GitHub releases created for both tags

**Validation:** 91 pytest tests passing.

---

## Backlog (Phase 2)

- `ruamel.yaml` migration (currently using `PyYAML` — see ADR-004)
- Singular test generation for mart models
- LLM response cache keyed on SHA-256(compiled_sql + config_fingerprint) — see ADR-005
- `--format json | markdown` output option for `audit`
- Manifest staleness warning (compare `generated_at` to model file mtimes)
- `--project-dir` flag for CI workflows — see ADR-011
- Announce on dbt Slack `#tools-and-integrations`
- Diátaxis documentation (tutorial, how-to, reference pages)

---

## v0.2.0 — `dbt-scribe catalog`

> **Scope:** Coverage audit command with terminal, HTML, and JSON output + CI gate.
> Read-only. No LLM calls. No file writes.
> Full spec in CDC v0.2.0 (Claude Desktop project).

---

### Step 12 — Catalog parser `step/12-catalog-parser` ✅

Parse `target/catalog.json` into typed dataclasses. Optional — graceful fallback
when file is absent.

- [x] `dbt_scribe/catalog/__init__.py`
- [x] `dbt_scribe/catalog/catalog_parser.py`
  - `parse_catalog(catalog_path: Path) -> dict[str, CatalogNode] | None`
    Returns None if file does not exist.
  - `CatalogNode` dataclass: `unique_id`, `name`, `columns: list[CatalogColumn]`
  - `CatalogColumn` dataclass: `name`, `data_type`, `comment`
  - Key: `unique_id` matches manifest node unique_id format
    (`model.<project>.<model_name>`)
- [x] `tests/catalog/__init__.py`
- [x] `tests/catalog/test_catalog_parser.py`
  - catalog.json present → parses correctly, returns dict keyed by unique_id
  - catalog.json absent → returns None
  - Columns extracted correctly (name, data_type)
  - Unknown/extra keys in catalog.json do not raise
- [x] Add `tests/fixtures/dbt_project/target/catalog.json`
      — minimal catalog fixture matching existing manifest fixture nodes
- [x] CI fix discovered during validation: preserve legacy
      `accepted_values.values` in `tests_generator` sanitizer

**Validation:** 102 pytest tests passing. Catalog parser tests: 15 passing.
Ruff clean for `dbt_scribe/catalog/`, `tests/catalog/`, and touched generator file.

---

### Step 13 — Coverage engine `step/13-coverage-engine`

Core computation logic. Takes manifest nodes + optional catalog + YAML models
and produces a typed `CoverageResult`.

- [ ] `dbt_scribe/catalog/coverage_engine.py`
  - New dataclasses: `ColumnCoverage`, `ModelCoverage`, `LayerCoverage`,
    `CoverageResult`, `CoverageThresholds`
  - `compute_coverage(nodes, catalog, yaml_models, config) -> CoverageResult`
  - Column merge: manifest columns ← supplement with catalog columns if present
  - Description check: delegates to existing `is_description_set()`
  - Test count: counts generic tests from existing YamlColumn.tests
  - Layer grouping: delegates to existing `detect_layer()`
  - Global scores: weighted average by column count across all models
- [ ] `tests/catalog/test_coverage_engine.py`
  - All models fully documented + tested → score = 100%
  - Model with no YAML → all columns count as undocumented
  - `catalog.json` present → catalog columns used for totals
  - `catalog.json` absent → manifest columns used
  - `{{ doc("...") }}` reference → counted as documented
  - Model with 0 columns → handled without ZeroDivisionError
  - Global score is weighted by column count (not simple average)
  - Per-layer aggregation is correct

**Validation:** cumulative tests passing

---

### Step 14 — Terminal reporter `step/14-terminal-reporter`

Rich table output. Refactors existing `coverage.py` into this module.

- [ ] `dbt_scribe/catalog/reporters/__init__.py`
- [ ] `dbt_scribe/catalog/reporters/terminal_reporter.py`
  - `render(result: CoverageResult, layer_filter: str | None = None) -> None`
  - Header: project name, model count, adapter
  - Per-layer section: layer name, model table, layer aggregate scores
  - Per-model row: name, description status (✅/❌), col doc %, test %, score
  - Global summary table: doc score vs threshold, test score vs threshold, status
  - Colour coding: green (≥ threshold), amber (within 20 pts), red (> 20 pts below)
  - All colour signals supplemented with text/icons (WCAG AA)
  - Compact mode when model count > 20 (hide column detail lists)
- [ ] `dbt_scribe/coverage.py` — refactored to delegate to `terminal_reporter`
      (existing public API preserved for backward compat)
- [ ] `tests/catalog/test_terminal_reporter.py`
  - Output contains project name and model names
  - Layer filter respected (only requested layer rendered)
  - Colour threshold logic tested (green/amber/red conditions)
  - Zero-model layer handled gracefully

---

### Step 15 — HTML reporter `step/15-html-reporter`

Self-contained HTML report generated via Jinja2.

- [ ] `dbt_scribe/templates/__init__.py` (or `templates/` as package data)
- [ ] `dbt_scribe/templates/catalog_report.html.j2`
  - Inline CSS (no external framework)
  - Vanilla JS for expand/collapse only
  - Sections: header, global gauges, layer cards, model detail table, footer
  - Print stylesheet
  - WCAG 2.1 AA: semantic HTML, no colour-only signaling, sufficient contrast
- [ ] `dbt_scribe/catalog/reporters/html_reporter.py`
  - `render(result: CoverageResult, output_path: Path) -> None`
  - Creates parent directories if needed
  - Renders template with CoverageResult data
- [ ] `pyproject.toml` — add `templates/` to `[tool.hatch.build.targets.wheel]`
      package data (or equivalent for the build backend in use)
- [ ] `tests/catalog/test_html_reporter.py`
  - File created at specified path
  - HTML contains project name, all model names, global scores
  - No external `src=` or `href=` pointing outside the file
  - Output path parent created automatically if missing

---

### Step 16 — JSON reporter `step/16-json-reporter`

Machine-readable JSON output for CI pipelines and downstream tooling.

- [ ] `dbt_scribe/catalog/reporters/json_reporter.py`
  - `render(result: CoverageResult) -> str`
  - Serializes to the schema defined in CDC §4.2
  - `generated_at` as ISO 8601 string
  - `passed` field reflects threshold check result
- [ ] `tests/catalog/test_json_reporter.py`
  - Valid JSON (parseable with `json.loads`)
  - All required top-level keys present
  - `generated_at` is ISO 8601
  - `models` array contains one entry per node
  - `undocumented_columns` and `untested_columns` are lists of strings

---

### Step 17 — CI gate `step/17-ci-gate`

Exit code enforcement when thresholds are not met.

- [ ] `dbt_scribe/catalog/ci_gate.py`
  - `check(result: CoverageResult, ci_mode: bool) -> int`
    Returns 0 (pass) or 1 (fail). Does NOT call sys.exit() — caller decides.
  - `format_failure_message(result: CoverageResult) -> str`
    Human-readable summary: which threshold(s) failed, by how much.
- [ ] `tests/catalog/test_ci_gate.py`
  - 100% branch coverage
  - ci_mode=False → always returns 0
  - ci_mode=True, all thresholds met → returns 0
  - ci_mode=True, doc below threshold → returns 1
  - ci_mode=True, test below threshold → returns 1
  - ci_mode=True, both below → returns 1
  - failure message contains threshold values and actual scores

---

### Step 18 — Wire up CLI `step/18-catalog-cli`

Wire all new modules into the Click CLI. Make `audit` a backward-compatible alias.

- [ ] `dbt_scribe/cli.py`
  - Add `catalog` command with all options:
    `--target`, `--output`, `--report-path`, `--threshold-docs`,
    `--threshold-tests`, `--ci`, `--format`, `--layer`
  - Make `audit` call `catalog` with `--output terminal --format table`
    (identical behaviour to v0.1.x)
  - Use `sys.exit(ci_gate.check(...))` at end of command when `--ci`
    or `fail_on_threshold: true`
- [ ] `dbt_scribe/config.py`
  - Add `CatalogConfig` Pydantic model
    (`report_path`, `open_after_generate`, `include_catalog`)
  - `CoverageConfig.fail_on_threshold` — now enforced (was declared but ignored)
- [ ] `dbt-scribe.yml` init template — add `catalog:` section with defaults
- [ ] `tests/test_cli_catalog.py`
  - `catalog` command runs without error on fixture project
  - `audit` alias produces identical output to `catalog --output terminal`
  - `--ci` flag triggers exit code check
  - `--output html` creates file at default path
  - `--output json` prints valid JSON to stdout
  - `--layer staging` filters output correctly
- [ ] End-to-end validation on DataBird bootcamp project:
  - `dbt-scribe catalog` terminal output looks correct
  - `dbt-scribe catalog --output html` → open and verify HTML manually
  - `dbt-scribe catalog --ci` → verify exit code (should be 0 or 1 depending
    on actual project coverage)
  - `dbt-scribe audit` → identical to v0.1.x output

---

### Step 19 — Documentation + release `step/19-release-v0.2.0`

- [ ] `CHANGELOG.md` — add `[0.2.0]` section with full feature list
- [ ] `README.md`
  - Update commands table (add `catalog`, note `audit` is now an alias)
  - Add `catalog` section with examples and option reference
  - Add CI integration section (GitHub Actions snippet)
  - Update roadmap table
- [ ] `CONTEXT.md` — update "What this project is" to include catalog command
- [ ] `NEXT_STEPS.md` — mark v0.2.0 steps complete, add v0.3.0 skeleton
- [ ] `STRUCTURE.md` — add `catalog/`, `reporters/`, `templates/` to repo tree
- [ ] `DECISIONS.md` — confirm ADRs 017–020 are present (added before step/12)
- [ ] PyPI publish `v0.2.0`
- [ ] GitHub release + tag `v0.2.0`

---

## Backlog (deferred from v0.2.0)

- `--fix` flag for `catalog`: chains `generate` on models below threshold → v0.2.1
- `ruamel.yaml` migration (currently using `PyYAML` — see ADR-004) → Phase 2
- Singular test generation for mart models → Phase 2
- LLM response cache keyed on SHA-256(compiled_sql + config_fingerprint) — ADR-005
- Manifest staleness warning (compare `generated_at` to model file mtimes)
- `--project-dir` flag for CI workflows — ADR-011
- Diátaxis documentation (tutorial, how-to, reference pages)
- Announce on dbt Slack `#tools-and-integrations`

---

## v0.3.0 — `dbt-scribe quality` (preview)

> Full CDC to be written before development begins.

- `dbt-scribe quality ingest` — parses `run_results.json`, persists to DuckDB
- `dbt-scribe quality report` — test pass/fail trends over time
- `dbt-scribe quality gate --ci` — exit code 1 on regression vs last run
- Persistent store: `~/.dbt-scribe/quality.duckdb`
- Flaky test detection (failure rate > configurable threshold)
- Shared HTML template infrastructure with `catalog`

## v0.3.x — OpenMetadata integration (preview)

> Gated behind `pip install dbt-scribe[openmetadata]`.

- `dbt-scribe catalog --output openmetadata`
- `dbt-scribe quality --output openmetadata`
- Pushes coverage + test run history to self-hosted OpenMetadata via REST API
