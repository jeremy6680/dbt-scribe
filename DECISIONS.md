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

| Provider              | Default model       | Environment variable | SDK package    |
| --------------------- | ------------------- | -------------------- | -------------- |
| `anthropic` (default) | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY`  | `anthropic`    |
| `openai`              | `gpt-4o`            | `OPENAI_API_KEY`     | `openai`       |
| `google`              | `gemini-2.5-pro`    | `GOOGLE_API_KEY`     | `google-genai` |

**Note on Google SDK:** The originally planned `google-generativeai` package was
deprecated before implementation. The `google-genai` package (Google's replacement,
`from google import genai`) is used instead. The interface is functionally equivalent.

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
`True` for any non-empty string OR any string matching the pattern `{{ doc("...") }}`.

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

---

## ADR-012 — `model_root` read from `dbt_project.yml`, not hardcoded

**Date:** 2026-05-08  
**Status:** Accepted

**Decision:** The path prefix used to locate model YAML files (default `"models"`) is
read from the `model-paths` key of `dbt_project.yml` at startup, rather than being
hardcoded as the string `"models"`.

**Rationale:** dbt's `model-paths` config is the authoritative source for where models
live. Hardcoding `"models"` would silently create files in the wrong directory (or miss
existing ones) for any project that sets `model-paths: [dbt_models]` or similar —
without raising an error, causing documentation corruption.

**Implementation:** `_read_model_root()` in `cli.py` reads `dbt_project.yml` (already
required by `_bootstrap()`) and extracts `model-paths[0]`, defaulting to `"models"` if
the key is absent. The value is stored in `ScribeConfig.model_root` via `model_copy()`
and threaded through to `yaml_writer`, `docs_writer`, and `resolver`.

**Consequence:** `ScribeConfig` gains a `model_root: str` field. It is not
user-configurable in `dbt-scribe.yml` — it is always derived from `dbt_project.yml` to
avoid duplicating config the user already maintains.

**Alternative rejected:** A `model_root` key in `dbt-scribe.yml`. Rejected because it
would require users to keep two files in sync.

---

## ADR-013 — Non-retryable HTTP status codes bypass the retry loop

**Date:** 2026-05-08  
**Status:** Accepted

**Decision:** `LLMProvider.complete()` does not retry exceptions whose `status_code`
attribute is in `{400, 401, 403, 404}`. These are re-raised immediately.

**Rationale:** Retrying authentication errors (401), permission errors (403), or
not-found errors (404) is wasteful and misleading — the result is identical on every
attempt, and the 0 + 2 + 4 second backoff adds 6 seconds of delay before the same
failure. The real root cause (missing API key, wrong model name) is also obscured by
the final "LLM call failed after 3 attempts" message.

**Implementation:** Provider-agnostic duck typing: `getattr(exc, "status_code", None)`.
The Anthropic, OpenAI, and Google SDKs all expose `status_code` on their HTTP exception
classes. No provider SDK is imported in `base_generator.py`.

**Consequence:** Only transient errors (network timeout, 429 rate limit, 5xx) benefit
from the retry loop.

---

## ADR-014 — sqlglot column extraction fallback when manifest columns dict is empty

**Date:** 2026-05-09
**Status:** Accepted

**Decision:** When `manifest.json` has an empty `columns` dict for a node (which happens
when no YAML existed at `dbt compile` time), extract column names from the compiled SQL
using sqlglot. Try the adapter dialect first (e.g. `bigquery` for backtick quoting), then
fall back through `bigquery → duckdb → postgres → None` until one succeeds.

**Rationale:** dbt only populates `columns` in the manifest from existing YAML declarations.
On a greenfield project with no YAML, the dict is always empty — which is exactly the
situation `dbt-scribe` is designed to fix. The multi-dialect fallback handles BigQuery's
backtick quoting which sqlglot rejects without the correct dialect.

**Consequence:** `manifest_parser.py` now imports sqlglot. Column names extracted from SQL
are lowercased and have no data_type or description (None). This is acceptable — the
generator only needs column names to produce descriptions and tests.

---

## ADR-015 — Mart docs block assembled in Python, not by LLM

**Date:** 2026-05-09
**Status:** Accepted

**Decision:** The four-section mart docs block structure is assembled in Python in
`docs_generator._assemble_mart_docs_block()`. The LLM is only asked to provide the
content of two sections (`description_and_motivation` and `known_limitations`) as
separate JSON fields. The section headers, blank lines, and stakeholder sections are
added by code.

**Rationale:** Prompt-only enforcement of the four-section template proved unreliable —
the LLM consistently returned a `docs_block_content` key with free-form markdown
regardless of how the prompt was worded. Moving structure to code guarantees the template
is always respected. The fallback in `_assemble_mart_docs_block` handles the case where
the LLM still returns `docs_block_content` by using it as the description section content.

**Consequence:** `docs_mart.j2` now requests separate JSON fields. The LLM response shape
changed from `{model_description, docs_block_content, columns}` to
`{model_description, description_and_motivation, known_limitations, columns}`.
The Python assembly guarantees the four sections regardless of LLM output.

---

## ADR-016 — Layer detection uses alternate spelling fallbacks

**Date:** 2026-05-09
**Status:** Accepted

**Decision:** `detect_layer()` in `analyzer.py` accepts common alternate spellings of
layer folder names (`mart` vs `marts`, `int` vs `intermediate`) in addition to exact
config matches.

**Rationale:** Real dbt projects use `mart/` (without s) while the CDC and default config
specify `marts/`. Requiring an exact match caused `Layer.UNKNOWN` on the test project,
which silently routed mart models through the staging prompt and bypassed
`_assemble_mart_docs_block`. Alternate spelling fallbacks make the tool robust to the
most common naming variations without requiring config changes.

**Consequence:** Users with non-standard folder names should still set `marts_prefix`
correctly in `dbt-scribe.yml` — the fallbacks are a safety net, not a replacement for
correct config.

---

## ADR-017 — `catalog` as new command, `audit` as backward-compatible alias

**Date:** 2026-05-17
**Status:** Accepted

**Decision:** Add `dbt-scribe catalog` as the primary audit command. `dbt-scribe audit`
becomes a backward-compatible alias that calls `catalog` with default options
(`--output terminal --format table`), producing identical output to v0.1.x.

**Rationale:** `catalog` better reflects the expanded scope of the command: coverage
audit + HTML report + JSON output + CI gate. Renaming avoids a breaking change for
existing users and CI pipelines already using `audit`. The alias approach means
no user migration is required.

**Rejected alternative:** Extend `audit` in place with new flags. Rejected because
the option surface grows significantly and the name `audit` undersells the command's
capabilities (reporting, CI enforcement) to new users.

---

## ADR-018 — `catalog.json` as optional column source

**Date:** 2026-05-17
**Status:** Accepted

**Decision:** `target/catalog.json` (produced by `dbt docs generate`) is read when
present and used to supplement manifest column data. When absent, the tool falls back
gracefully to manifest columns only, preserving v0.1.x behaviour.

**Rationale:** `catalog.json` provides warehouse-introspected column lists, which are
more complete than manifest columns when no YAML existed at compile time (the ADR-014
scenario). It also avoids the sqlglot fallback path for column discovery in the catalog
context. Using it is strictly additive — it never replaces manifest data, only fills gaps.

**Trade-off:** Full accuracy requires users to run `dbt docs generate` in addition to
`dbt compile`. This is documented but not enforced. The fallback ensures the command
remains useful without this step.

---

## ADR-019 — HTML report via Jinja2, self-contained, no frontend framework

**Date:** 2026-05-17
**Status:** Accepted

**Decision:** The HTML catalog report is generated by rendering a Jinja2 template
with inline CSS and vanilla JS. No React, no Tailwind build step, no CDN dependencies.

**Rationale:** The report must be self-contained: shareable as a single file, usable
offline, committable to a repo, attachable to a PR comment. A frontend build step
would require Node.js as a dev dependency, which is out of scope for a Python CLI
and would conflict with the "drop into any dbt project" installation story.

Jinja2 is already a dependency (prompt templates), so this adds no new packages.

**Constraint:** Interactivity is limited to expand/collapse via vanilla JS. Charts
and dynamic filtering are deferred — the report is a static snapshot, not a dashboard.

---

## ADR-020 — `dbt-scribe[catalog]` optional dependency group (forward-compat)

**Date:** 2026-05-17
**Status:** Accepted

**Decision:** Declare a `[catalog]` optional dependency group in `pyproject.toml`,
even though v0.2.0 introduces no new required packages (Jinja2 is already a dep).

**Rationale:** v0.3.x will add the `metadata-ingestion` SDK (OpenMetadata Python
client, ~200 MB) as a heavy optional dependency gated behind
`pip install dbt-scribe[openmetadata]`. Establishing the `[catalog]` group pattern
now means the install convention is consistent across v0.2.x and v0.3.x, and users
are not surprised by a new install pattern when OpenMetadata lands.

**Note:** For v0.2.0, `pip install dbt-scribe` and `pip install dbt-scribe[catalog]`
are functionally identical. The distinction becomes meaningful in v0.3.x.

---

## ADR-021 — Preserve legacy `accepted_values.values` during test sanitization

**Date:** 2026-05-17
**Status:** Accepted

**Decision:** The generic test sanitizer preserves `values` as an allowed
configuration key for `accepted_values` tests, in addition to the dbt 1.10.5+
`arguments` format.

**Rationale:** v0.1.x prompts prefer the newer `arguments: {values: [...]}` syntax,
but existing tests and possible LLM responses may still return the legacy direct
`values: [...]` form. The sanitizer's job is to remove unsafe or hallucinated keys,
not to erase valid dbt test arguments. Dropping `values` caused an existing generator
test to fail during Step 12 full-suite validation.

**Consequence:** `accepted_values` tests are accepted in both forms:
`{"accepted_values": {"name": "...", "values": [...]}}` and
`{"accepted_values": {"name": "...", "arguments": {"values": [...]}}}`.
Future normalization can convert legacy syntax to the canonical `arguments` form,
but Step 12 keeps the fix minimal and backward-compatible.

---

## ADR-022 — ruamel.yaml for round-trip YAML serialisation

**Date:** 2026-05-19
**Status:** Accepted

**Decision:** Migrate from PyYAML to `ruamel.yaml` (round-trip mode) for all YAML
read/write operations in dbt-scribe.

**Rationale:** PyYAML's `safe_dump` does not preserve comments, quote styles, or
multi-line string formatting. This caused dbt-scribe to reformat hand-written or
previously generated YAML files on every write, producing cosmetic diffs that
triggered false `changed=True` results and corrupted user formatting.

ruamel.yaml in `typ="rt"` (round-trip) mode preserves comments and formatting when
loading and re-serialising existing files. New files are written with a clean
`YAML()` instance for consistent, predictable output.

**Constraint:** ruamel.yaml's round-trip is not perfectly transparent for all YAML
constructs (e.g. manually formatted multi-line block sequences). Semantic change
detection uses a JSON snapshot of the model entry before/after merge to avoid
false positives regardless of serialisation differences.

---

## ADR-023 — Shared YAML file discovery via directory tree walk

**Date:** 2026-05-19
**Status:** Accepted

**Decision:** `find_yaml_source()` locates the YAML file where a model is already
declared by scanning all `.yml` files in the model's directory, then walking up
ancestor directories until `model_root` is reached.

**Rationale:** dbt projects commonly use one shared YAML file per layer
(e.g. `intermediate/_intermediate__models.yml`) while model `.sql` files live in
sub-directories (e.g. `intermediate/books/int_books__unified.sql`). The previous
approach guessed a per-model filename which never matched shared files, causing
`catalog` to report 0% coverage and `generate`/`docs`/`tests` to create duplicate
per-model YAML files alongside the existing shared ones.

**Consequence:** `write_yaml()` accepts a `source_path` parameter. When a shared
file is found, the model entry is merged in-place and the file is rewritten only
if the model entry semantically changed. When no existing file is found, a new
per-model file is created as before (v0.1.x behaviour preserved for new projects).

---

## ADR-024 — Test deduplication by type, not by full dict equality

**Date:** 2026-05-19
**Status:** Accepted

**Decision:** `_append_missing_tests` deduplicates generated tests against existing
tests using the top-level test key (e.g. `accepted_values`, `not_null`) rather than
full dict equality.

**Rationale:** Existing tests in hand-written YAML often carry extra keys (`config`,
`name`, `severity`) that the LLM does not generate. Full dict equality caused
duplicates to be appended on every run because `{"accepted_values": {"arguments":
{"values": [...]}}}` != `{"accepted_values": {"arguments": {"values": [...]},
"config": {"where": "..."}, "name": "..."}}`.

**Constraint:** One test per type per column. If a user has two `accepted_values`
tests on the same column (unusual but valid in dbt), dbt-scribe will not add a
second one. This is acceptable — the common case is one test per type.
