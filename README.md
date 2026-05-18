# dbt-scribe

[![CI](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/dbt-scribe.svg)](https://pypi.org/project/dbt-scribe/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**LLM-powered documentation and test generation for dbt Core projects.**

`dbt-scribe` analyses your dbt project and uses an LLM (Anthropic Claude, OpenAI, or
Google Gemini) to automatically generate model descriptions, column descriptions, and
data tests — following your project's conventions, never overwriting what already exists.
It also audits documentation and test coverage with `dbt-scribe catalog`.

---

## The problem

Writing thorough dbt documentation and tests is non-negotiable — but it is slow.
A staging model with 15 columns takes 30–45 minutes to document properly when following
strict conventions: English descriptions, two-tier docs blocks, named tests, shared
column blocks, four-section mart template.

Existing tools don't fully solve this:

| Tool                | Limitation                                                               |
| ------------------- | ------------------------------------------------------------------------ |
| `dbt-osmosis`       | Mechanical propagation — no LLM understanding                            |
| `dbt-codegen`       | Generates empty boilerplate only                                         |
| `dbt Assist`        | Cloud-only, paid, not configurable                                       |
| `dbt-coverage`      | Measures coverage but generates nothing                                  |
| dbt Power User ext. | VS Code only, AI features require a paid SaaS subscription (Altimate AI) |

`dbt-scribe` fills the gap: **LLM-powered generation, headless, CI/CD-ready,
configurable per project, compatible with dbt Core.**

---

## How dbt-scribe compares

Several tools exist to help with dbt documentation and test generation.
Here is where `dbt-scribe` stands:

| Capability                               | dbt-scribe | dbt Power User | dbt Assist | dbt-osmosis |
| ---------------------------------------- | :--------: | :------------: | :--------: | :---------: |
| LLM-powered generation                   |     ✅     |       ✅       |     ✅     |     ❌      |
| Works without VS Code                    |     ✅     |       ❌       |     ❌     |     ✅      |
| CI/CD integration (exit code)            |     ✅     |       ❌       |     ❌     |     ❌      |
| Your own API key (no SaaS)               |     ✅     | ❌ (paid tier) | ❌ (paid)  |     n/a     |
| Multi-provider (Anthropic/OpenAI/Google) |     ✅     |       ❌       |     ❌     |     n/a     |
| Config versioned with project            |     ✅     |       ❌       |     ❌     |     ✅      |
| Convention-aware (layers, PK/FK, enums)  |     ✅     |   ⚠️ partial   | ⚠️ partial |     ❌      |
| Audit without generation                 |     ✅     |       ❌       |     ❌     |     ❌      |
| Open source (MIT)                        |     ✅     |       ❌       |     ❌     |     ✅      |

**dbt Power User** is an excellent IDE extension for individual developers who want
UI-assisted generation while editing in VS Code. `dbt-scribe` targets a different
workflow: automated quality enforcement that runs in a terminal, a Docker container,
or a CI pipeline — with no IDE dependency and no third-party SaaS subscription.

The two tools are complementary, not mutually exclusive.

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

Available on [PyPI](https://pypi.org/project/dbt-scribe/).

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
dbt-scribe catalog --target models/
```

No LLM calls, nothing written. Shows documentation and test coverage by layer.

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

| Command | Purpose |
| --- | --- |
| `dbt-scribe init` | Create `dbt-scribe.yml` |
| `dbt-scribe docs` | Generate documentation only |
| `dbt-scribe tests` | Generate tests only |
| `dbt-scribe generate` | Generate docs and tests together |
| `dbt-scribe catalog` | Report documentation/test coverage in terminal, HTML, or JSON |
| `dbt-scribe audit` | Backward-compatible alias for the terminal catalog report |

### `dbt-scribe init`

Generates a `dbt-scribe.yml` configuration file at the project root.

```bash
dbt-scribe init
```

If `dbt-scribe.yml` already exists, edit it directly or remove it before running
`init` again.

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

### `dbt-scribe catalog`

Reports documentation and test coverage across a dbt project. No generation,
no LLM calls, and no model files are written.

```bash
dbt-scribe catalog --target <path>
```

Common examples:

```bash
# Terminal report
dbt-scribe catalog --target models/

# Self-contained HTML report
dbt-scribe catalog --output html --report-path target/dbt-scribe-catalog.html

# Machine-readable JSON matching the catalog schema
dbt-scribe catalog --output json

# Filter to one layer
dbt-scribe catalog --layer staging

# Fail CI when configured thresholds are not met
dbt-scribe catalog --ci
```

Options:

| Option | Description |
| --- | --- |
| `--target <path>` | File, directory, or project root to audit |
| `--output terminal|html|json` | Select terminal, HTML file, or JSON stdout output |
| `--report-path <file>` | Destination for `--output html` |
| `--threshold-docs <pct>` | Override configured documentation threshold |
| `--threshold-tests <pct>` | Override configured test threshold |
| `--ci` | Return exit code 1 when thresholds fail |
| `--format table|json` | Backward-compatible output format alias |
| `--layer <name>` | Filter to `staging`, `intermediate`, or `marts` |

For the most complete column totals, run `dbt docs generate` before `catalog` so
`target/catalog.json` is available. If it is absent, `dbt-scribe` falls back to
manifest columns.

---

### `dbt-scribe audit`

Backward-compatible alias for the terminal catalog report.

```bash
dbt-scribe audit --target <path>
```

---

## Configuration (`dbt-scribe.yml`)

Generated by `dbt-scribe init` and versioned with your dbt project.
Key settings:

```yaml
llm:
  provider: anthropic # anthropic | openai | google
  model: claude-sonnet-4-6
  temperature: 0.2 # Low for consistent, structured output

docs:
  two_tier: true # Short desc in YAML, long desc in *__docs.md
  shared_columns: # These columns use shared docs blocks
    - created_at
    - updated_at
    - _fivetran_synced
  default_owner: "Data Team"
  default_contact: ""

tests:
  pk_patterns: ["^.*_id$", "^id$"]
  fk_patterns: ["^.*_fk$"]
  enum_patterns: ["^.*_type$", "^.*_status$", "^.*_category$"]

coverage:
  min_doc_coverage: 80 # % threshold for catalog / CI mode
  min_test_coverage: 60
  fail_on_threshold: false

catalog:
  report_path: target/dbt-scribe-catalog.html
  open_after_generate: false
  include_catalog: true

conventions:
  staging_prefix: staging
  intermediate_prefix: intermediate
  marts_prefix: marts
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
7. **Catalog** — reads manifest metadata, optional warehouse catalog metadata, and
   existing YAML docs/tests to compute coverage reports without calling an LLM

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

| Provider              | Default model       | Environment variable |
| --------------------- | ------------------- | -------------------- |
| `anthropic` (default) | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY`  |
| `openai`              | `gpt-4o`            | `OPENAI_API_KEY`     |
| `google`              | `gemini-2.5-pro`    | `GOOGLE_API_KEY`     |

Only the key for your configured provider is required.

---

## CI integration

Use `dbt-scribe catalog --ci` in your pipeline to enforce documentation and test
coverage thresholds. You can also set `fail_on_threshold: true` in
`dbt-scribe.yml` to make `catalog` fail automatically when thresholds are not met:

```yaml
# .github/workflows/dbt-quality.yml
- name: Check dbt documentation coverage
  run: |
    dbt compile
    dbt docs generate
    dbt-scribe catalog --target models/ --ci --output json
```

```yaml
# dbt-scribe.yml
coverage:
  min_doc_coverage: 80
  min_test_coverage: 60
  fail_on_threshold: true

catalog:
  report_path: target/dbt-scribe-catalog.html
  include_catalog: true
```

---

## Project structure

```
dbt-scribe/
├── dbt_scribe/
│   ├── cli.py                  # Click entry point — all commands and catalog reports
│   ├── config.py               # Pydantic config + provider resolution
│   ├── resolver.py             # Resolves --target to a list of models
│   ├── analyzer.py             # Layer detection + column type inference
│   ├── parsers/
│   │   ├── manifest_parser.py  # Reads target/manifest.json
│   │   └── yaml_parser.py      # Reads existing .yml files
│   ├── catalog/
│   │   ├── catalog_parser.py   # Reads optional target/catalog.json
│   │   ├── coverage_engine.py  # Computes CoverageResult coverage data
│   │   ├── ci_gate.py          # CI exit-code decision and failure messages
│   │   └── reporters/          # Terminal, HTML, and JSON catalog reporters
│   ├── generators/
│   │   ├── base_generator.py   # LLMProvider ABC + retry logic
│   │   ├── providers/          # anthropic | openai | google
│   │   ├── docs_generator.py
│   │   └── tests_generator.py
│   ├── writers/
│   │   ├── yaml_writer.py      # Create from scratch or merge
│   │   └── docs_writer.py      # Create or append *__docs.md
│   ├── prompts/                # Jinja2 prompt templates per layer
│   └── templates/              # Packaged report templates
└── tests/
    └── fixtures/dbt_project/   # Minimal dbt project with pre-built manifest/catalog
```

The test suite uses checked-in fixtures and mocked LLM providers — CI requires
no dbt installation, no warehouse connection, and no API keys.

---

## Roadmap

| Phase                     | Status      | Highlights                                                      |
| ------------------------- | ----------- | --------------------------------------------------------------- |
| Phase 1 — MVP             | ✅ Complete | `docs`, `tests`, `generate`, `audit` commands                   |
| Phase 2 — Catalog         | ✅ Complete | `catalog` terminal/HTML/JSON reports and CI gate                |
| Phase 3 — Quality         | 📋 Planned  | Test run history, trend monitoring, quality gate                |
| Phase 3.x — Metadata      | 📋 Planned  | OpenMetadata integration                                        |

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Jeremy Marchandeau — [web2data.org](https://web2data.org)
