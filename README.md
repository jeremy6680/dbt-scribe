# dbt-scribe

[![CI](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/jeremy6680/dbt-scribe/actions/workflows/ci.yml)

LLM-powered documentation and test generation for dbt Core projects.

## Current MVP

`dbt-scribe` runs from a dbt project root and requires:

- `dbt_project.yml`
- `target/manifest.json`
- `dbt-scribe.yml`

Run `dbt compile` before using generation commands so the manifest is current.

```bash
dbt-scribe docs --target models/ --dry-run
dbt-scribe tests --target models/ --dry-run
dbt-scribe generate --target models/ --dry-run
dbt-scribe audit --target models/
```

The test suite uses checked-in dbt fixtures and mocked providers, so CI does not
require dbt, a warehouse, or LLM network calls.
