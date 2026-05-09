# dbt-scribe

[![CI](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**LLM-powered documentation and test generation for dbt Core projects.**

`dbt-scribe` analyses your dbt project and uses an LLM (Anthropic Claude, OpenAI, or
Google Gemini) to automatically generate model descriptions, column descriptions, and
data tests — following your project's conventions, never overwriting what already exists.

---

## The problem

Writing thorough dbt documentation and tests is non-negotiable — but it is slow.
A staging model with 15 columns takes 30–45 minutes to document properly when following
strict conventions: English descriptions, two-tier docs blocks, named tests, shared
column blocks, four-section mart template.

Existing tools don't fully solve this:

| Tool           | Limitation                                    |
| -------------- | --------------------------------------------- |
| `dbt-osmosis`  | Mechanical propagation — no LLM understanding |
| `dbt-codegen`  | Generates empty boilerplate only              |
| `dbt Assist`   | Cloud-only, paid, not configurable            |
| `dbt-coverage` | Measures coverage but generates nothing       |

`dbt-scribe` fills the gap: **LLM-powered generation, local, configurable per project,
compatible with dbt Core.**

---

## What it generates

**Documentation**

- Model descriptions (inline YAML or long-form docs blocks)
- Column descriptions for every undocumented column
- `*__docs.md` files following dbt's two-tier convention
- Four-section template for mart docs blocks (Description / Limitations / Business
  Stakeholder / Technical Stakeholder)

**Tests**

- Named generic tests in YAML: `not_null`, `unique`, `accepted_values`, `relationships`
- Column types are inferred automatically (primary key, foreign key, enum, timestamp,
  boolean, metric) to generate the right tests
- `accepted_values` lists are inferred from `CASE WHEN` and `WHERE IN` clauses in
  compiled SQL — a placeholder `TODO` is generated when values cannot be detected

**Safe by default**

- Only fills in what is missing — never overwrites existing descriptions or tests
- A `{{ doc("...") }}` reference is treated as a filled description and is preserved
- Use `--force` to regenerate everything, including existing content
- Use `--dry-run` to preview output without writing any files

---

## Requirements

- Python 3.11+
- dbt Core (any version that produces `target/manifest.json`)
- A supported dbt adapter: **DuckDB**, **BigQuery**, or **PostgreSQL**
- An API key for your chosen LLM provider

---

## Installation

```bash
pip install dbt-scribe
```

Or install from source for local development:

```bash
git clone https://github.com/jeremy6680/dbt-scribe.git
cd dbt-scribe
pip install -e .
```

---

## Quickstart

**All commands must be run from the root of your dbt project** (the directory
containing `dbt_project.yml`).

### 1. Compile your dbt project

`dbt-scribe` reads compiled SQL from `target/manifest.json`. Run this first and
any time your models change:

```bash
dbt compile
```

### 2. API key

`dbt-scribe` requires an API key for the LLM provider configured in `dbt-scribe.yml`
(default: Anthropic Claude).

Add the key to your shell profile so it is available in every session:

```bash
# Add to ~/.zprofile (Mac) or ~/.bashrc (Linux)
export ANTHROPIC_API_KEY=sk-ant-...

# Reload your shell profile
source ~/.zprofile
```

> **Mac note:** Use `~/.zprofile`, not `~/.zshrc`. On Mac, terminal apps open as
> login shells and load `~/.zprofile` first. Variables set only in `~/.zshrc` may
> not be available inside virtual environments.

Other supported providers:

```bash
export OPENAI_API_KEY=sk-...    # for provider: openai
export GOOGLE_API_KEY=...       # for provider: google
```

### 3. Initialise the config

```bash
dbt-scribe init
```

This generates a `dbt-scribe.yml` at your project root. Open it and set your
preferred LLM provider, coverage thresholds, shared column names, and layer conventions.
Commit this file — it is part of your project.

### 4. Check current coverage

```bash
dbt-scribe audit --target models/
```

No LLM calls, nothing written. Shows doc and test coverage per model.

### 5. Preview generation (dry run)

```bash
# Documentation only
dbt-scribe docs --target models/ --dry-run

# Tests only
dbt-scribe tests --target models/ --dry-run

# Both in one pass
dbt-scribe generate --target models/ --dry-run
```

### 6. Generate for real

```bash
dbt-scribe generate --target models/
```

---

## Commands

All commands must be run from the **root of your dbt project**
(the directory containing `dbt_project.yml`).

### `dbt-scribe init`

Generates a `dbt-scribe.yml` configuration file at the project root.

```bash
dbt-scribe init [--force]
```

`--force` overwrites an existing `dbt-scribe.yml`.

---

### `dbt-scribe docs`

Generates model and column descriptions. Writes inline YAML descriptions and
long-form `*__docs.md` docs blocks.

```bash
dbt-scribe docs --target <path> [--dry-run] [--force]
```

```bash
# Single model
dbt-scribe docs --target models/staging/spotify/stg_spotify__tracks.sql

# All models in a folder
dbt-scribe docs --target models/staging/

# Entire project
dbt-scribe docs --target models/

# Preview without writing
dbt-scribe docs --target models/ --dry-run
```

---

### `dbt-scribe tests`

Generates named generic tests in YAML.

```bash
dbt-scribe tests --target <path> [--dry-run] [--force]
```

---

### `dbt-scribe generate`

Generates documentation **and** tests in a single LLM call per model.

```bash
dbt-scribe generate --target <path> [--dry-run] [--force]
```

---

### `dbt-scribe audit`

Reports documentation and test coverage per model. No generation, no LLM calls.

```bash
dbt-scribe audit --target <path>
```

Example output:

```
Audit summary

stg_spotify__tracks:   doc coverage 100% (19/19), test coverage 0%   (0/19)
stg_spotify__albums:   doc coverage  60%  (6/10), test coverage 0%   (0/10)
int_music__unified:    doc coverage 100% (14/14), test coverage 0%  (0/14)
mrt_music__collection: doc coverage 100% (13/13), test coverage 0%  (0/13)
```

---

## Configuration (`dbt-scribe.yml`)

Generated by `dbt-scribe init` and versioned with your dbt project.
Key settings:

```yaml
llm:
  provider: anthropic # anthropic | openai | google
  model: claude-sonnet-6
  temperature: 0.2 # Low for consistent, structured output

docs:
  language: en
  two_tier: true # Short desc in YAML, long desc in *__docs.md
  shared_columns: # These columns use shared docs blocks
    - _loaded_at
    - created_at
  mart_template: true # Enforce four-section template for mart docs

tests:
  named_tests: true # All generic tests use the name: key
  pk_patterns: ["_id$", "^id$"]
  enum_patterns: ["_status$", "_type$"]

coverage:
  min_doc_coverage: 80 # % threshold for audit / CI mode
  min_test_coverage: 60

conventions:
  layers:
    staging:
      prefixes: ["stg_", "base_"]
    intermediate:
      prefixes: ["int_"]
    marts:
      prefixes: [] # No prefix — detected by exclusion
        # Override if your project uses e.g. ["mrt_"]
```

---

## How it works

1. **Bootstrap** — validates that `dbt_project.yml`, `target/manifest.json`, and
   `dbt-scribe.yml` are all present in the current directory
2. **Manifest parsing** — reads compiled SQL (Jinja2-resolved), column lists, lineage,
   adapter type, and fully-qualified node names from `target/manifest.json`
3. **YAML parsing** — reads existing `.yml` files to detect what is already documented
4. **Analysis** — detects the layer (staging / intermediate / marts) and infers column
   types (pk, fk, enum, timestamp, boolean, metric, shared, text)
5. **Generation** — calls the configured LLM with structured prompts; all responses
   are JSON for reliable parsing — one call per model, not per column
6. **Writing** — creates `.yml` files from scratch or merges non-destructively into
   existing ones; creates or appends to `*__docs.md` files

> **Why `manifest.json` and not the `.sql` files directly?**
> dbt model files contain unresolved Jinja2 (`{{ ref('...') }}`, `{{ var('...') }}`,
> macros). `target/manifest.json`, produced by `dbt compile`, contains fully-resolved
> SQL — the only reliable source for column extraction and expression analysis.

---

## Supported adapters

| Adapter    | Status       | Notes                                  |
| ---------- | ------------ | -------------------------------------- |
| DuckDB     | ✅ Supported | Default for local / portfolio projects |
| BigQuery   | ✅ Supported | Auto-detected from manifest metadata   |
| PostgreSQL | ✅ Supported | Auto-detected from manifest metadata   |

Adapter is auto-detected from `manifest.json`. You can override it in `dbt-scribe.yml`.

---

## LLM providers

| Provider              | Default model              | Environment variable |
| --------------------- | -------------------------- | -------------------- |
| `anthropic` (default) | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY`  |
| `openai`              | `gpt-4o`                   | `OPENAI_API_KEY`     |
| `google`              | `gemini-2.5-pro`           | `GOOGLE_API_KEY`     |

Only the key for your configured provider is required.

---

## CI integration

Use `dbt-scribe audit` in your pipeline to enforce documentation and test coverage
thresholds. Set `fail_on_threshold: true` in `dbt-scribe.yml` to exit with code 1
when thresholds are not met:

```yaml
# .github/workflows/dbt-quality.yml
- name: Check dbt documentation coverage
  run: |
    dbt compile
    dbt-scribe audit --target models/ --ci
```

```yaml
# dbt-scribe.yml
coverage:
  min_doc_coverage: 80
  min_test_coverage: 60
  fail_on_threshold: true
```

---

## Project structure

```
dbt-scribe/
├── dbt_scribe/
│   ├── cli.py                  # Click entry point — all commands
│   ├── config.py               # Pydantic config + provider resolution
│   ├── resolver.py             # Resolves --target to a list of models
│   ├── analyzer.py             # Layer detection + column type inference
│   ├── parsers/
│   │   ├── manifest_parser.py  # Reads target/manifest.json
│   │   └── yaml_parser.py      # Reads existing .yml files
│   ├── generators/
│   │   ├── base_generator.py   # LLMProvider ABC + retry logic
│   │   ├── providers/          # anthropic | openai | google
│   │   ├── docs_generator.py
│   │   └── tests_generator.py
│   ├── writers/
│   │   ├── yaml_writer.py      # Create from scratch or merge
│   │   └── docs_writer.py      # Create or append *__docs.md
│   └── prompts/                # Jinja2 prompt templates per layer
└── tests/
└── fixtures/dbt_project/   # Minimal dbt project with pre-built manifest
```

The test suite uses checked-in fixtures and mocked LLM providers — CI requires
no dbt installation, no warehouse connection, and no API keys.

---

## Roadmap

| Phase                     | Status      | Highlights                                                      |
| ------------------------- | ----------- | --------------------------------------------------------------- |
| Phase 1 — MVP             | ✅ Complete | `docs`, `tests`, `generate`, `audit` commands                   |
| Phase 2 — Portfolio-ready | 🔄 Planned  | Singular SQL tests, LLM cache, `ruamel.yaml` migration, CI mode |
| Phase 3 — Open source     | 📋 Backlog  | PyPI publication, full documentation, dbt Slack announcement    |

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Jeremy Marchandeau — [web2data.org](https://web2data.org)
