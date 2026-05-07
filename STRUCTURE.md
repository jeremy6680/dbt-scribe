# STRUCTURE.md — dbt-scribe

Folder and file structure of the `dbt-scribe` repository.

> **Important distinction:** This file documents the structure of the `dbt-scribe`
> tool's own repository. For the structure that `dbt-scribe` *generates inside a
> dbt project*, see the "Output structure" section at the bottom.

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
│   ├── analyzer.py                     # Layer detection, column type inference, EnrichedModel builder
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── manifest_parser.py          # Reads target/manifest.json → ManifestNode list
│   │   │                               # Extracts: compiled SQL, columns, fqn, lineage, adapter
│   │   └── yaml_parser.py              # Reads existing .yml files → YamlModel
│   │                                   # Detects filled descriptions incl. {{ doc("...") }} refs
│   │
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── base_generator.py           # LLMProvider ABC + LLMResponse dataclass + retry logic
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── anthropic_provider.py   # Anthropic Claude — uses ANTHROPIC_API_KEY
│   │   │   ├── openai_provider.py      # OpenAI GPT — uses OPENAI_API_KEY
│   │   │   └── google_provider.py      # Google Gemini — uses GOOGLE_API_KEY
│   │   ├── docs_generator.py           # Calls LLM to generate descriptions + docs blocks
│   │   └── tests_generator.py          # Calls LLM to generate generic tests YAML
│   │
│   ├── writers/
│   │   ├── __init__.py
│   │   ├── yaml_writer.py              # Creates .yml from scratch OR merges into existing .yml
│   │   │                               # Non-destructive: preserves filled descriptions and tests
│   │   ├── docs_writer.py              # Creates/appends to *__docs.md files
│   │   └── singular_test_writer.py     # Writes SQL singular test files into tests/ (Phase 2)
│   │
│   ├── coverage.py                     # Computes and renders coverage report (doc + test %)
│   │
│   └── prompts/                        # Jinja2 prompt templates — one per layer × generation type
│       ├── docs_staging.j2             # Docs prompt for staging models
│       ├── docs_intermediate.j2        # Docs prompt for intermediate models
│       ├── docs_mart.j2                # Docs prompt for mart models (includes four-section template)
│       ├── tests_generic.j2            # Generic tests prompt (all layers)
│       └── tests_singular.j2           # Singular tests prompt (marts only — Phase 2)
│
├── tests/                              # pytest test suite for dbt-scribe itself
│   ├── conftest.py                     # Shared fixtures (config, provider mocks, sample nodes)
│   ├── fixtures/
│   │   └── dbt_project/                # Minimal dbt project used as test input
│   │       ├── dbt_project.yml
│   │       ├── dbt-scribe.yml          # Test configuration
│   │       ├── target/
│   │       │   └── manifest.json       # Pre-generated manifest — tests do not require dbt installed
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
│   ├── test_manifest_parser.py
│   ├── test_yaml_parser.py
│   ├── test_analyzer.py
│   ├── test_providers.py               # All three providers tested with mocked HTTP responses
│   ├── test_docs_generator.py
│   ├── test_tests_generator.py
│   ├── test_yaml_writer.py
│   ├── test_docs_writer.py
│   └── test_coverage.py
│
├── .env.example                        # Documents all supported API key variables
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                      # ruff + mypy + pytest on push and PR
├── pyproject.toml                      # Package metadata, dependencies, CLI entry point, ruff config
├── README.md                           # User-facing documentation (written in Phase 2)
├── CHANGELOG.md                        # Version history (written at first release)
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
- Passes `--dry-run`, `--force`, `--target`, `--config` options down to the pipeline

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

Raw `.sql` files are never read directly (see ADR-007 and ADR-009).

### `dbt_scribe/analyzer.py`

Takes a `ManifestNode` and produces an `EnrichedModel` with typed columns.

Layer detection uses the `fqn` from the manifest (e.g.,
`["project", "staging", "api_sports", "stg_api_sports__fixtures"]` → `staging`).

Column type inference applies, in priority order:
1. Config patterns (`pk_patterns`, `fk_patterns`, `enum_patterns`)
2. `shared_columns` list from docs config
3. Name heuristics (`is_`/`has_`/`did_` → boolean, `_at`/`_date` → timestamp)
4. SQL expression heuristics (aggregation functions → metric, arithmetic → calculated)
5. Default: `text`

### `dbt_scribe/generators/base_generator.py`

Defines the `LLMProvider` abstract interface. All three provider implementations
expose a single method: `complete(system: str, user: str) -> LLMResponse`.
This means `docs_generator.py` and `tests_generator.py` are completely decoupled
from SDK specifics.

Retry logic (3 attempts, exponential backoff) lives here and is inherited by all providers.

### `dbt_scribe/writers/yaml_writer.py`

The most complex writer. Two modes:

**Create from scratch** (no `.yml` exists):
Generates a complete, canonical YAML file with section comments, columns ordered by
type (PK → FK → timestamps → enums → metrics/calculated → shared), `persist_docs`
for staging and marts only, and tags inferred from the manifest `fqn`.

**Merge** (`.yml` exists):
Uses `is_description_set()` to determine what can be overwritten. Existing filled
descriptions (including `{{ doc("...") }}` references) are preserved unless `--force`.
Existing tests are never deleted; only missing tests are appended.

### `tests/fixtures/dbt_project/target/manifest.json`

A hand-crafted or pre-generated manifest that covers all the scenarios tested:
- Staging model with partial YAML (merge mode)
- Intermediate model with no YAML (create from scratch)
- Mart model with no YAML (create from scratch, four-section template)
- Columns of all inferred types (pk, fk, enum, timestamp, boolean, metric, shared)

Tests never require `dbt` to be installed or a warehouse connection to be active.

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
