# LogLens — Build Plan (V2: AI understanding layer)

Target tag: **v0.2.0**. Builds on the V1 codebase (`BUILD_PLAN.md`), reusing its two seams —
the `Flow` object and the `Analyzer` protocol — so nothing here rewrites the deterministic
core. Same rules: lightweight, stdlib-first, `src/` layout, heavy deps behind optional extras,
test-gated, one focused test file per module.

Goal: help the architect *interpret* the flow — surface likely problems and summarize what
happened — while keeping the deterministic parts model-free. The deterministic gap detection
ships independent of any LLM, so it is sequenced first and is **not** blocked by the provider
decision.

**Prime Claude Code first:**
```
Read DESIGN.md and the existing src/loglens code. We are now building V2 on top of
this codebase, one module at a time, reusing the Flow object and the Analyzer
protocol already defined. Same rules as before: lightweight, stdlib-first, src/
layout, heavy deps behind optional extras, every module gets a focused pytest file
with effort proportional to its complexity. Do not write code yet — confirm you've
read the code and are ready for the first step.
```

Decision gates marked ⚑ must be resolved before the steps beneath them.

---

## Phase V2.1 — Gap & anomaly heuristics (deterministic, no LLM)

### Step V2.1.1 — gaps.py
```
Create src/loglens/gaps.py. Define a small dataclass Annotation
(flow_id, record_seq, kind, detail). Implement detect_gaps(flow: Flow) ->
list[Annotation] with three structural detectors, all deterministic:
- dangling_start: a record whose template looks like an entry
  (started|begin|received|entering|opening) with no matching terminal
  (finished|done|sent|completed|closed|failed|error) later in the same flow.
- downgraded_error: a record whose message or fields contain an exception/stack
  signature (e.g. "Traceback", "Exception", "Error:", " at ") but whose level is
  below ERROR.
- unresolved_retry: a record matching (retry|retrying|attempt \d+) with no
  later success/terminal record in the flow.
Keyword lists live at module top, case-insensitive, easy to extend. Pure
functions, no I/O.

Then tests/test_gaps.py: one synthetic flow per detector with a known defect
(assert it fires) and one clean flow (assert zero annotations — the
false-positive guard matters most). Run and fix until green.
```
**Accept when:** each detector fires on its defect and stays silent on clean flows.

## Phase V2.2 — Declared expectation rules (optional)

### Step V2.2.1 — expectations.py
```
Create src/loglens/expectations.py. Support a tiny YAML rule format:
  - after: <template substring or template_id>
    expect_one_of: [<substring>, ...]
    within_trace: true
Use PyYAML (add "yaml" only if not already present; it is small).
load_rules(path) -> list[Rule]; check(flow, rules) -> list[Annotation] (reuse the
Annotation from gaps.py): for each matched "after" record, if none of
expect_one_of appears later in the same flow, emit a violation annotation.

Then tests/test_expectations.py: a satisfied rule -> no annotation; a violated
rule -> one annotation. Run and fix until green.
```
**Accept when:** satisfied rules are silent, violations are flagged with detail.

### ⚑ Decision gate V2.A — LLM provider strategy
Resolve before Phase V2.3. Pick one:
- **API provider** (OpenAI-compatible / Anthropic HTTP): fastest to validate, online,
  needs a key. Recommended to build first.
- **Local provider** (llama.cpp via `llama-cpp-python`, or Ollama): offline, heavier setup.
- **Both behind one interface**: build the interface + API now, add local later.

Recommendation: build the `LLMProvider` interface plus one API implementation now (behind a
`[llm]` extra), and leave a local implementation as a later drop-in. Keeps the offline core
untouched and the provider swappable.

## Phase V2.3 — Provider abstraction

### Step V2.3.1 — providers.py
```
Create src/loglens/providers.py. Define an LLMProvider Protocol with a single
method: complete(prompt: str, max_tokens: int = 512) -> str. Implement the
provider chosen in decision gate V2.A behind an optional extra (add "llm" to
optional-dependencies in pyproject.toml). Lazy-import the client inside __init__;
raise a clear RuntimeError with the `pip install loglens[llm]` hint if missing.
Read credentials/endpoint from explicit args or env vars, never hardcoded. Also
provide a trivial EchoProvider(LLMProvider) in the same module that returns a
deterministic transformation of the prompt — for use in tests so no real network
call is needed.

Then tests/test_providers.py using EchoProvider only: assert the Protocol is
satisfied and complete() returns a string. Run and fix until green.
```
**Accept when:** the interface is defined, the real provider is import-guarded, and
`EchoProvider` lets tests run with no network.

## Phase V2.4 — Flow summarization

### Step V2.4.1 — summarize via the Analyzer seam
```
Extend src/loglens/analyzer.py: implement the summarize(flow: Flow,
provider: LLMProvider, gaps: list[Annotation] | None = None) -> str method left
as a stub in V1. Build a compact, bounded prompt from the flow: flow_id, origin,
ordered list of (ts, level, source, template) with repeated templates collapsed,
plus any gap annotations. Truncate very long flows to a configurable max number
of events so the prompt stays bounded. Ask the model to (1) summarize what
happened and (2) flag anything that looks skipped, swallowed, or out of order.
Return the provider's text.

Then tests/test_summarize.py using EchoProvider: assert the prompt embeds the
flow's templates and gap details, and that summarize returns the provider output.
Never call a real LLM in tests. Run and fix until green.
```
**Accept when:** the prompt is well-formed and bounded; tests pass with `EchoProvider`.

### Step V2.4.2 — wire summarize into facade + CLI
```
Add LogLens.summarize(flow_id, provider=None) — default to constructing the
configured provider, run detect_gaps first and pass annotations in. Add a CLI
flag --summarize FLOW_ID that prints the summary, and --gaps that prints
detect_gaps output for all flows (deterministic, needs no provider). Without the
llm extra, --summarize prints the install hint and exits cleanly; --gaps always
works. Commit as "feat: gap detection + flow summarization (v0.2)".
```
**Accept when:** `--gaps` works with zero extra deps; `--summarize` works with `[llm]`.

## Phase V2.5 — lineage preset

### Step V2.5.1 — lineage.py
```
Create src/loglens/lineage.py: trace(records, value: str) -> list[LogRecord]
returns, in order, every record whose fields values or message contain the given
value (e.g. a user id, order id). Add a CLI flag --lineage VALUE that renders
just those records across all flows, with their flow_id shown, so the architect
can follow one entity through the system.

Then tests/test_lineage.py: a fixture where one id appears in 3 of 6 records ->
assert exactly those 3 come back in order. Run and fix until green.
Bump version to 0.2.0, update README with the new flags, commit, tag v0.2.0.
```
**Accept when:** lineage returns the right ordered subset; v0.2.0 tagged.

---

## V2 layout additions
```
src/loglens/gaps.py · expectations.py · providers.py · lineage.py
(analyzer.py extended)   tests: one per new module
optional extra: [llm]   (yaml added to deps)
```

Next: `BUILD_PLAN_V3.md` (live runtime tracing).
