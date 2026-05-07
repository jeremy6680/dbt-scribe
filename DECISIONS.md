# DECISIONS.md — dbt-scribe

Architectural and technical decisions log.
Each entry documents what was decided, why, and what alternatives were considered.

---

## ADR-001 — Multi-provider LLM abstraction from V1

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** Support three LLM providers from V1 (Anthropic Claude, OpenAI, Google
Gemini) through a shared `LLMProvider` abstract interface.

**Rationale:** Provider preference is a legitimate user choice (cost, access, model
quality). Implementing the abstraction upfront costs little (one interface + three
simple adapters) and avoids a painful refactor later. All providers receive identical
prompts (structured JSON, temperature 0.2), making the abstraction natural.

**Providers:**

| Provider             | Default model              | Environment variable  |
|----------------------|----------------------------|-----------------------|
| `anthropic` (default)| `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY`   |
| `openai`             | `gpt-4o`                   | `OPENAI_API_KEY`      |
| `google`             | `gemini-2.5-pro`           | `GOOGLE_API_KEY`      |

**Consequence:** Three SDK dependencies instead of one. All three are installed by
default; optional extras may be introduced in V2 if package size becomes a concern.

**Alternative rejected:** Claude-only in V1, abstraction in V2. Rejected because the
interface is trivial to write now and would cause an API-breaking change later.

---

## ADR-002 — Structured JSON output from LLM

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** All LLM calls must return valid JSON only. The system prompt explicitly
forbids any text outside the JSON structure (no preamble, no markdown fences,
no explanation).

**Rationale:** JSON parsing is reliable and deterministic. Free-text responses would
require fragile regex-based extraction that breaks on minor model output variations.

**Consequence:** Prompts must be carefully engineered to prevent the model from adding
explanatory text. A JSON parse failure triggers a retry (up to 3 attempts).

---

## ADR-003 — One LLM call per model, not per column

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** Generate documentation and tests for all columns of a model in a single
LLM call.

**Rationale:** A single call gives the model full inter-column context (e.g., it can
infer that `home_score` and `away_score` are paired concepts). It also reduces API
cost and latency compared to one call per column.

**Consequence:** Prompts can be long for wide models. If a model exceeds ~50 columns,
the call will be split into two sequential calls to stay within context limits.

---

## ADR-004 — `ruamel.yaml` instead of `PyYAML`

**Date:** 2026-05-07  
**Status:** Accepted (deferred to Phase 2 — `PyYAML` used in Phase 1 for simplicity)

**Decision:** Use `ruamel.yaml` for all YAML read/write operations in the final tool.

**Rationale:** `PyYAML` does not preserve comments or key ordering in round-trip
operations. dbt YAML files use structured comments (`# ── Primary key ──`) as
visual separators that must be preserved when merging into existing files.

**Consequence:** `ruamel.yaml` has a slightly more verbose API than `PyYAML`.
Phase 1 uses `PyYAML` to keep the initial scope small; migration to `ruamel.yaml`
is scheduled for Phase 2 (Step tracked in NEXT_STEPS.md backlog).

---

## ADR-005 — Cache key = SHA-256(compiled_sql + config_fingerprint)

**Date:** 2026-05-07  
**Status:** Accepted (deferred to Phase 2)

**Decision:** LLM response cache keys are computed from a composite hash of the
compiled SQL and the relevant sections of `dbt-scribe.yml`.

**Rationale:** Hashing compiled SQL alone is insufficient — if `dbt-scribe.yml`
changes (new patterns, new `default_owner`, new thresholds), cached results may no
longer match the expected output even if the SQL is unchanged.

**Implementation:**
```python
config_fingerprint = json.dumps({
    "llm": config.llm.model_dump(),
    "docs": config.docs.model_dump(),
    "tests": config.tests.model_dump(),
    "conventions": config.conventions.model_dump(),
}, sort_keys=True)
cache_key = hashlib.sha256((compiled_sql + config_fingerprint).encode()).hexdigest()
```

**Consequence:** `.dbt-scribe-cache/` directory must be added to `.gitignore`.
A config change invalidates all cache entries for affected models.

---

## ADR-006 — `dbt-scribe.yml` lives in the dbt project root

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** The configuration file is versioned inside the target dbt project,
not in a global user directory.

**Rationale:** Each dbt project has its own conventions (adapter, coverage thresholds,
shared column names, owner details). The config must evolve with the project and be
visible to anyone cloning the repo.

**Consequence:** `dbt-scribe` looks for `dbt-scribe.yml` in the current working
directory. A missing config file triggers a `BootstrapError` with an explicit
suggestion to run `dbt-scribe init`.

---

## ADR-007 — `sqlglot` applied to compiled SQL only (never to raw `.sql` files)

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** `sqlglot` is used exclusively to parse the compiled SQL extracted from
`manifest.json`. Raw `.sql` files (which contain unresolved Jinja2 templates) are
never passed to `sqlglot`.

**Rationale:** `sqlglot` is an excellent multi-dialect SQL parser, but dbt `.sql`
files contain Jinja2 (`{{ ref('...') }}`, `{{ var('...') }}`, custom macros) that
`sqlglot` cannot handle. Using compiled SQL (where Jinja2 is fully resolved by dbt)
eliminates this friction entirely.

**Consequence:** `sql_parser.py` does not exist. All SQL parsing logic lives in
`manifest_parser.py` (extraction from manifest) and `analyzer.py` (calling `sqlglot`
on the extracted compiled SQL).

**Alternative rejected:** Naive Jinja2 pre-processing (replace `{{ ... }}` with
placeholders). Rejected because it is fragile and impossible to test exhaustively.

---

## ADR-008 — YAML Writer creates missing files from scratch

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** `dbt-scribe` creates `.yml` files from scratch when they do not exist,
rather than requiring a pre-existing skeleton from `dbt-codegen`.

**Rationale:** Makes the tool fully autonomous. Users can run `dbt-scribe generate`
on a dbt project that has no YAML documentation at all and get a complete, correctly
structured result. `dbt-codegen` remains compatible but is no longer required.

**Consequence:** The YAML Writer must know the canonical structure expected per layer
(section comments, column ordering, conditional `persist_docs`, tags inferred from
the manifest `fqn`).

**Alternative rejected:** Require a pre-existing empty `.yml` file. Rejected because
it introduces unnecessary friction (two-tool workflow for a task that should be one command).

---

## ADR-009 — `manifest.json` is a mandatory prerequisite

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** `target/manifest.json` is required for all commands except `init`.
There is no degraded mode that operates without the manifest in V1.

**Rationale:** Raw `.sql` files contain Jinja2 that cannot be reliably parsed without
running dbt. The manifest, produced by `dbt compile`, contains fully-resolved compiled
SQL — the only reliable source for column extraction.

**User impact:** The user must run `dbt compile` before using `dbt-scribe`. This is
documented prominently in the README and enforced by the bootstrap check with an
explicit error message including the command to run.

**Alternative rejected:** Best-effort mode on raw SQL (Jinja2 replaced by placeholders).
Rejected because results would be unreliable and difficult to test. The `dbt compile`
prerequisite is a low-friction, well-understood workflow step.

**V2 consideration:** A `--no-manifest` flag could enable partial analysis on raw SQL
for cases where compiling the project is not possible (e.g., missing warehouse credentials).

---

## ADR-010 — `{{ doc("...") }}` reference treated as a filled description

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** The YAML Writer treats a column description containing `{{ doc("...") }}`
as "already documented" and will not overwrite it unless `--force` is passed.

**Rationale:** A `doc()` reference is intentional documentation. Overwriting it
automatically would silently break carefully hand-crafted YAML files.

**Implementation:** `is_description_set(description)` in `yaml_parser.py` returns
`True` for any non-empty string OR any string matching the pattern `{{\s*doc\(`.

**Consequence:** `--force` is the only mechanism to replace an existing `doc()` reference
with a generated inline description.

---

## ADR-011 — Run from dbt project root, no `--project-dir` flag in V1

**Date:** 2026-05-07  
**Status:** Accepted

**Decision:** `dbt-scribe` must be invoked from the dbt project root directory.
No `--project-dir` flag is provided in V1.

**Rationale:** Keeps all path resolution relative to `os.getcwd()`, consistent with
how `dbt` itself works. Simpler bootstrap logic.

**Consequence:** The bootstrap check validates `dbt_project.yml` in the current
directory and exits with a clear error if it is absent.

**Alternative rejected:** Auto-discovery (walking up parent directories to find
`dbt_project.yml`). Rejected because implicit behavior is hard to debug and
could produce surprising results in nested project structures.

**V2:** A `--project-dir` flag will be added to support CI workflows that invoke
tools from a repository root that is not the dbt project root.
