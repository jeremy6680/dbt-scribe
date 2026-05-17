# STRUCTURE.md — dbt-scribe

Folder and file structure of the `dbt-scribe` repository.

> **Important distinction:** This file documents the structure of the `dbt-scribe`
> tool's own repository. For the structure that `dbt-scribe` _generates inside a
> dbt project_, see the "Output structure" section at the bottom.

---

## Repository structure

```
dbt-scribe/
│
├── dbt_scribe/                         # Main Python package
│   ├── __init__.py                     # Package version
│   ├── cli.py                          # Click entry point — all commands + bootstrap validation
│   ├── config.py                       # Pydantic models for dbt-scribe.yml + provider resolution
│   ├── resolver.py                     # Resolves --target (file / dir / project) → list of nodes
│   ├── analyzer.py                     # Layer/column typing + EnrichedModel/EnrichedColumn builder
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── manifest_parser.py          # Reads target/manifest.json → ManifestNode list
│   │   │                               # ManifestNode + ManifestColumn dataclasses
│   │   │                               # Extracts: compiled SQL, columns, fqn, lineage, adapter
│   │   └── yaml_parser.py              # Reads existing .yml files → YamlModel
│   │                                   # YamlModel + YamlColumn dataclasses
│   │                                   # Detects filled descriptions incl. {{ doc("...") }} refs
│   │
│   ├── catalog/
│   │   ├── __init__.py
│   │   └── catalog_parser.py           # Reads optional target/catalog.json → CatalogNode dict
│   │                                   # CatalogNode + CatalogColumn dataclasses
│   │                                   # Model nodes only; lowercases warehouse column names
│   │
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── base_generator.py           # LLMProvider ABC + LLMResponse dataclass + retry logic
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── anthropic_provider.py   # Anthropic Claude — uses ANTHROPIC_API_KEY
│   │   │   ├── openai_provider.py      # OpenAI GPT — uses OPENAI_API_KEY
│   │   │   └── google_provider.py      # Google Gemini — uses GOOGLE_API_KEY
│   │   ├── docs_generator.py           # Renders docs prompts + parses DocsResult JSON
│   │   └── tests_generator.py          # Renders test prompts + parses TestsResult JSON
│   │
│   ├── writers/
│   │   ├── __init__.py
│   │   ├── yaml_writer.py              # Creates .yml from scratch OR merges into existing .yml
│   │   │                               # Non-destructive: preserves filled descriptions and tests
│   │   ├── docs_writer.py              # Creates/appends to *__docs.md files
│   │   └── singular_test_writer.py     # Writes SQL singular test files into tests/ (Phase 2)
│   │
│   ├── coverage.py                     # Legacy audit report entrypoint (doc + test %)
│   │
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── catalog_parser.py           # Parses optional target/catalog.json into typed model/column metadata
│   │   ├── coverage_engine.py          # Pure coverage computation over manifest + catalog + YAML state
│   │   └── reporters/
│   │       ├── __init__.py
│   │       └── terminal_reporter.py    # Rich terminal rendering for CoverageResult
│   │
│   └── prompts/                        # Jinja2 prompt templates — one per layer × generation type
│       ├── docs_staging.j2             # Docs prompt for staging models
│       ├── docs_intermediate.j2        # Docs prompt for intermediate models
│       ├── docs_mart.j2                # Docs prompt for mart models (four-section template)
│       ├── tests_generic.j2            # Generic tests prompt (all layers)
│       └── tests_singular.j2           # Singular tests prompt (marts only — Phase 2)
│
├── tests/                              # pytest test suite for dbt-scribe itself
│   ├── fixtures/
│   │   └── dbt_project/                # Minimal dbt project used as test input
│   │       ├── dbt_project.yml
│   │       ├── dbt-scribe.yml          # Test configuration
│   │       ├── target/
│   │       │   ├── manifest.json       # Pre-generated manifest — 4 nodes covering all test scenarios (DuckDB stg/int/mart + BigQuery empty-columns node)
│   │       │   └── catalog.json        # Pre-generated catalog — matching model nodes + warehouse column metadata
│   │       └── models/
│   │           ├── staging/
│   │           │   └── api_sports/
│   │           │       ├── stg_api_sports__fixtures.sql       # Raw SQL (not used directly)
│   │           │       └── stg_api_sports__fixtures.yml       # Partially filled — tests merge logic
│   │           ├── intermediate/
│   │           │   └── rugby/
│   │           │       └── int_fixtures_enriched_with_teams.sql
│   │           └── marts/
│   │               └── rugby/
│   │                   └── fixtures.sql                        # No .yml — tests create-from-scratch
│   ├── test_config.py
│   ├── test_bootstrap.py
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── test_catalog_parser.py      # Optional catalog.json parser coverage
│   │   ├── test_coverage_engine.py     # Pure coverage engine aggregation and edge cases
│   │   └── test_terminal_reporter.py   # Rich terminal reporter output, filters, colours, compact mode
│   ├── test_manifest_parser.py
│   ├── test_yaml_parser.py
│   ├── test_analyzer.py
│   ├── test_providers.py               # All three providers tested with mocked SDK clients
│   ├── test_docs_generator.py
│   ├── test_tests_generator.py
│   ├── test_yaml_writer.py
│   ├── test_docs_writer.py
│   ├── test_integration_pipeline.py
│   ├── test_regressions.py             # Regression tests for all e2e bugs (9 scenarios)
│   └── test_coverage.py
│
├── .env.example                        # Documents all supported API key variables
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                      # ruff + mypy + pytest on push and PR (in that order)
├── pyproject.toml                      # Package metadata, dependencies, CLI entry point, ruff config
├── README.md                           # MVP overview, CI badge, and quickstart commands
├── CHANGELOG.md                        # Version history
├── CONTEXT.md                          # Project overview for contributors and AI assistants
├── DECISIONS.md                        # Architectural decision records (ADRs)
├── NEXT_STEPS.md                       # Current development priorities and step-by-step plan
└── STRUCTURE.md                        # This file
```

---

## Key files explained

### `dbt_scribe/cli.py`

Entry point for all CLI commands. Responsibilities:

- Defines the Click command group `dbt-scribe`
- Runs the bootstrap check before every command except `init`
  (validates `dbt_project.yml`, `target/manifest.json`, `dbt-scribe.yml` in CWD)
- Commands: `init`, `docs`, `tests`, `generate`, `audit`
- Wires the main pipeline: config → manifest parsing → target resolution →
  YAML parsing → analyzer → generators → writers
- Supports `--target`, `--dry-run`, and `--force` for generation commands
- `audit` reports per-model documentation and test coverage without generation

### `dbt_scribe/resolver.py`

Resolves `--target` values against manifest nodes. Supports project-root targets,
model directories, individual `.sql` model files, and matching `.yml` files.

### `dbt_scribe/config.py`

Loads and validates `dbt-scribe.yml` using Pydantic v2. Also resolves the correct
`LLMProvider` instance from the configured provider name and the corresponding
environment variable.

### `dbt_scribe/parsers/manifest_parser.py`

The most important parser. Reads `target/manifest.json` and extracts everything
`dbt-scribe` needs to work:

- Compiled SQL (Jinja2-resolved) — used by the analyzer and sent to the LLM as context
- Column names and data types as declared in the manifest
- Fully-qualified node name (`fqn`) — used for layer detection and tag inference
- `depends_on.nodes` — upstream lineage for FK inference
- `metadata.adapter_type` — DuckDB / BigQuery / PostgreSQL

It returns model nodes only (`resource_type == "model"`) as `ManifestNode`
instances, with each column represented by a `ManifestColumn`.

Raw `.sql` files are never read directly (see ADR-007 and ADR-009).

### `dbt_scribe/parsers/yaml_parser.py`

Reads existing dbt YAML files and returns the first model as a `YamlModel`, with
columns represented by `YamlColumn`. Missing files return `None`, so downstream
pipeline code can distinguish create-from-scratch from merge mode.

It extracts model descriptions, column descriptions, and existing generic tests
from both `data_tests` and `tests`. `is_description_set()` treats any non-empty
description, including a `{{ doc(...) }}` reference, as already filled.

### `dbt_scribe/catalog/catalog_parser.py`

Reads optional `target/catalog.json` output from `dbt docs generate`. Missing files
return `None`, allowing later catalog/audit flows to fall back to manifest-only mode.

Only `nodes` are parsed; `sources` are ignored. Only node `unique_id` values beginning
with `model.` are included, matching manifest parser filtering. Column names are
lowercased for consistent matching with manifest/YAML columns, while warehouse
`type` and `comment` values are preserved as `CatalogColumn.data_type` and
`CatalogColumn.comment`. Missing or null comments become empty strings.

### `dbt_scribe/catalog/coverage_engine.py`

Computes documentation and test coverage as pure data. It combines manifest model
nodes, optional catalog columns, existing YAML documentation/tests, and configured
thresholds into a `CoverageResult`.

The engine does not render, call LLMs, or write files. It is the shared input for
catalog reporters and future CI gating.

### `dbt_scribe/catalog/reporters/terminal_reporter.py`

Renders a `CoverageResult` to the terminal with Rich. Output includes a project
header panel, one table per dbt layer, and a global documentation/test threshold
summary.

Colour-coded scores always include text or icons as well, so terminal output never
relies on colour alone. For projects above 20 models, the reporter switches to a
compact mode that shows percentages instead of per-model `X/Y` column details.

### `dbt_scribe/analyzer.py`

Takes a `ManifestNode` and produces an `EnrichedModel` with typed columns.
The enriched model combines manifest metadata, existing YAML documentation/tests,
compiled SQL expressions, and `needs_doc` / `needs_tests` flags used by later
generation and writer steps.

Layer detection uses the `fqn` from the manifest (e.g.,
`["project", "staging", "api_sports", "stg_api_sports__fixtures"]` → `staging`).

Column type inference applies, in priority order:

1. Config patterns (`pk_patterns`, `fk_patterns`, `enum_patterns`)
2. `shared_columns` list from docs config
3. Name heuristics (`is_`/`has_`/`did_` → boolean, `_at`/`_date` → timestamp)
4. SQL expression heuristics (aggregation functions → metric, arithmetic → calculated)
5. Default: `text`

Compiled SQL expressions are extracted with `sqlglot`; raw `.sql` files remain out
of scope per ADR-007.

### `dbt_scribe/generators/base_generator.py`

Defines the `LLMProvider` abstract interface. All three provider implementations
expose a single method: `complete(system: str, user: str) -> LLMResponse`.
This means `docs_generator.py` and `tests_generator.py` are completely decoupled
from SDK specifics.

Retry logic (3 attempts, exponential backoff) lives here and is inherited by all providers.

### `tests/test_providers.py`

Tests Anthropic, OpenAI, and Google provider adapters with fake SDK clients. These
tests verify request wiring and normalized `LLMResponse` output without making any
network calls.

### `dbt_scribe/generators/docs_generator.py`

Renders the layer-specific documentation prompt (`staging`, `intermediate`, or
`marts`), calls the configured `LLMProvider`, and parses strict JSON into a
`DocsResult`. Mart prompts require the four-section documentation template.

### `dbt_scribe/generators/tests_generator.py`

Renders the generic tests prompt, calls the configured `LLMProvider`, and parses
strict JSON into a `TestsResult`. It also applies deterministic safeguards for
generic tests: primary-key columns receive `not_null` and `unique`, and enum
columns receive an `accepted_values` placeholder if the LLM omits one.

LLM output is sanitized to keep only standard dbt generic tests and known-safe
configuration keys. Both accepted values formats are preserved: legacy direct
`values: [...]` and dbt 1.10.5+ `arguments: {values: [...]}`.

### `dbt_scribe/writers/yaml_writer.py`

Writes model YAML files and returns a `WriterResult` with path, changed flag, and
rendered content. Two modes:

**Create from scratch** (no `.yml` exists):
Generates a YAML file for the model path derived from `ManifestNode.path`.

**Merge** (`.yml` exists):
Uses `is_description_set()` to determine what can be overwritten. Existing filled
descriptions (including `{{ doc("...") }}` references) are preserved unless `--force`.
Existing tests are never deleted; only missing tests are appended.

### `dbt_scribe/writers/docs_writer.py`

Writes long-form dbt docs blocks and returns a `WriterResult`. It creates the
appropriate `*__docs.md` file if missing, appends new `{% docs %}` blocks to
existing files, and skips writes when a block for the model already exists.

### `tests/fixtures/dbt_project/target/manifest.json`

A hand-crafted or pre-generated manifest that covers all the scenarios tested:

- Staging model with partial YAML (merge mode)
- Intermediate model with no YAML (create from scratch)
- Mart model with no YAML (create from scratch, four-section template)
- Columns of all inferred types (pk, fk, enum, timestamp, boolean, metric, shared)

Tests never require `dbt` to be installed or a warehouse connection to be active.

### `tests/fixtures/dbt_project/target/catalog.json`

A hand-crafted catalog fixture matching the manifest model `unique_id` values. It
contains BigQuery-style warehouse column types, comments, absent/null comment cases,
and a catalog-only extra column used to verify that catalog metadata can supplement
manifest/YAML metadata.

---

## Output structure (what dbt-scribe writes into a dbt project)

When `dbt-scribe generate` runs on a dbt project, it writes or updates:

```
<dbt-project-root>/
│
├── models/
│   ├── staging/
│   │   └── <source>/
│   │       ├── stg_<source>__<entity>.yml          ← created or merged
│   │       └── _<source>__docs.md                  ← created or appended
│   ├── intermediate/
│   │   └── <domain>/
│   │       ├── int_<entities>_<verb>.yml            ← created or merged
│   │       └── _int_<domain>__docs.md               ← created or appended
│   └── marts/
│       └── <domain>/
│           ├── <entity>.yml                         ← created or merged
│           └── _<domain>__docs.md                   ← created or appended
│
└── tests/
    └── test__mart__<model>__<what>.sql              ← created (Phase 2, marts only)
```

Nothing outside these paths is modified. The source `.sql` files are never touched.

---

## What is NOT in this repository

- The Cahier des Charges (CDC) — kept in the Claude Desktop project, not committed
- `profiles.yml` — never committed (contains warehouse credentials)
- `.env` — never committed (contains API keys)
- `.dbt-scribe-cache/` — LLM response cache, gitignored
