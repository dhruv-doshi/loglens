# LogLens — Build Plan (V2: understanding, tracing & ecosystem)

Target tag: **v0.2.0**. Builds on the V1 codebase, reusing its single seam — the `Flow`
object — so nothing here rewrites the deterministic core. This plan merges what were
previously three separate plans (AI understanding, live tracing, agent ecosystem) into one
coherent version, and it is **deterministic and offline throughout: no generative LLM**.

> **Scope note — no LLM.** Earlier drafts included an `LLMProvider` abstraction and
> LLM-based flow *summarization*. Those are removed. V2 keeps only model-free,
> explainable analysis (structural gap detection + declared expectation rules) and the
> deterministic runtime tracer. The one machine-learning feature in the package remains
> the V1 semantic **query** (`EmbeddingQuery`), which uses a small sentence-embedding
> model behind the existing optional `[ai]` extra — it is not a generative LLM and is
> untouched here.

Same rules as V1: lightweight, stdlib-first, `src/` layout, heavy deps behind optional
extras, test-gated, one focused test file per module. The only new hard dependency is
`PyYAML` (small, for expectation rules); the runtime tracer and renderers are pure stdlib.

**Prime Claude Code first:**
```
Read DESIGN.md and the existing src/loglens code. We are now building V2 on top of
this codebase, one module at a time, reusing the Flow object already defined. V2 is
fully deterministic and offline — NO generative LLM. Same rules as before:
lightweight, stdlib-first, src/ layout, heavy deps behind optional extras, every
module gets a focused pytest file with effort proportional to its complexity. Do not
write code yet — confirm you've read the code and are ready for the first step.
```

Decision gates marked ⚑ must be resolved before the steps beneath them.

---

## Part A — Understanding layer (deterministic, no model)

### Phase V2.1 — Gap & anomaly heuristics

#### Step V2.1.1 — gaps.py
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

### Phase V2.2 — Declared expectation rules (optional)

#### Step V2.2.1 — expectations.py
```
Create src/loglens/expectations.py. Support a tiny YAML rule format:
  - after: <template substring or template_id>
    expect_one_of: [<substring>, ...]
    within_trace: true
Use PyYAML (add "PyYAML" to dependencies in pyproject.toml; it is small).
load_rules(path) -> list[Rule]; check(flow, rules) -> list[Annotation] (reuse the
Annotation from gaps.py): for each matched "after" record, if none of
expect_one_of appears later in the same flow, emit a violation annotation.

Then tests/test_expectations.py: a satisfied rule -> no annotation; a violated
rule -> one annotation; load_rules round-trips a YAML file. Run and fix until green.
```
**Accept when:** satisfied rules are silent, violations are flagged with detail.

### Phase V2.3 — Lineage preset

#### Step V2.3.1 — lineage.py
```
Create src/loglens/lineage.py: trace(records, value: str) -> list[LogRecord]
returns, in order, every record whose fields values or message contain the given
value (e.g. a user id, order id).

Then tests/test_lineage.py: a fixture where one id appears in 3 of 6 records ->
assert exactly those 3 come back in order. Run and fix until green.
```
**Accept when:** lineage returns the right ordered subset.

### Phase V2.4 — Wire understanding features into facade + CLI

#### Step V2.4.1 — facade + CLI flags
```
Extend src/loglens/lens.py and cli.py with the deterministic analysis features:
- LogLens.gaps() -> dict[flow_id, list[Annotation]]: run detect_gaps over every
  flow. LogLens.check_expectations(rules_path) -> list[Annotation]: load rules and
  run expectations.check over every flow. LogLens.lineage(value) -> list[LogRecord]
  over all stored records.
- CLI: --gaps prints detect_gaps output for all flows; --expect RULES.yaml prints
  expectation violations; --lineage VALUE renders just the matching records across
  all flows with their flow_id shown, so the architect can follow one entity through
  the system. All three are deterministic and need no extra deps.

Then extend tests/test_lens.py and tests/test_cli.py to cover --gaps and --lineage
end-to-end. Run and fix until green. Commit as
"feat: gap detection, expectation rules, lineage (v0.2 part A)".
```
**Accept when:** `--gaps`, `--expect`, and `--lineage` all work with zero extra deps.

---

## Part B — Live runtime tracing (stdlib only, no new deps)

Goal: add a second *ingestion* mechanism — instrument running code, capture the call tree
with zero code changes, and emit it as the **same `Flow` object** so the existing renderer
and gap detection work on it unchanged.

### ⚑ Decision gate V2.B — tracing backend
Resolve before Phase V2.5:
- **`sys.setprofile`** — works on all supported versions (3.10+), simple API, higher overhead.
- **`sys.monitoring`** (PEP 669) — 3.12+ only, much lower overhead, slightly more API.

Recommendation: build the `sys.setprofile` backend first (portable across the 3.10+ target),
behind a backend seam so a `sys.monitoring` backend can be added later for 3.12+ users without
changing callers.

### Phase V2.5 — Tracer core

#### Step V2.5.1 — tracer.py
```
Create src/loglens/tracer.py. A Tracer class usable as a context manager:
- __init__(include: list[str], capture_args: bool = False, max_events: int =
  100_000). `include` is a list of path/package prefixes; only calls whose code
  filename starts with one of them are recorded (this keeps stdlib out and bounds
  volume). capture_args defaults OFF.
- On enter: install the hook via sys.setprofile for the current thread AND
  threading.setprofile so threads started afterward are traced too. On exit:
  uninstall both.
- The hook handles 'call' / 'return' / 'c_call' events: maintain a per-thread
  call stack; on call push a CallEvent (qualname, module, filename, lineno,
  depth, thread_id, t_enter); on return set t_exit and pop. When capture_args is
  on, repr() each arg and truncate to a max length; otherwise store nothing.
  Respect max_events (stop recording past the cap, set a truncated flag).
- events() -> list[CallEvent].

Then tests/test_tracer.py: trace a tiny function that calls two helpers; assert
the captured names, depths, and parent/child order; assert a stdlib call (e.g.
json.dumps) is NOT recorded; assert capture_args is off by default. Run and fix
until green.
```
**Accept when:** the call tree is captured with correct nesting, stdlib is filtered, args
are off by default.

### Phase V2.6 — Trace → Flow

#### Step V2.6.1 — trace_to_flow.py
```
Create src/loglens/trace_to_flow.py: to_flows(events: list[CallEvent]) ->
list[Flow]. Map each CallEvent to a LogRecord (message and template = qualname,
ts = t_enter, source = module, fields carry depth/lineno/duration). Group into
flows by (thread_id + outermost call root) and synthesize flow ids like
"trace-0001". Reuse build_flows for ordering. The result must render with the
existing render.py unchanged.

Then tests/test_trace_to_flow.py: feed a hand-built event list, assert the Flow
grouping and that render_flows produces a tree. Run and fix until green.
```
**Accept when:** traces become `Flow`s that the existing renderer handles with no changes.

### Phase V2.7 — Concurrency honesty

#### Step V2.7.1 — threads & async
```
Harden tracer.py for concurrency:
- Threads: confirm threading.setprofile causes new threads to be traced; each
  thread id becomes its own flow grouping.
- Async: if asyncio.current_task() is available at call time, include the task id
  in the grouping key; otherwise mark those flows origin "trace (async,
  best-effort)" because coroutines interleave on one thread and cannot be cleanly
  separated — mirror the honest labeling used for synthesized log flows in V1.

Then extend tests: a threaded example yields separate flows; an async example is
grouped by task or carries the best-effort label. Run and fix until green.
```
**Accept when:** threaded runs separate cleanly; async runs are grouped or honestly labeled.

### Phase V2.8 — Wire tracing into facade + CLI

#### Step V2.8.1 — facade + CLI trace entry
```
Add to LogLens: a trace(include, capture_args=False) context manager that runs
user code under the Tracer and ingests the resulting flows into the same store as
logs, so show() and gaps() all work over traced flows. Add a CLI entry
`loglens trace -m <module>` that imports and runs a module under the tracer and
prints the flow tree. Add a short README section stating tracing is for dev/debug
only (overhead) and that max_events bounds memory.

Then tests/test_trace_integration.py: trace a small callable via the context
manager and assert show() includes the traced flow. Run and fix until green.
Commit as "feat: stdlib runtime call tracer -> Flow (v0.2 part B)".
```
**Accept when:** code traced via the facade renders alongside logs.

---

## Part C — Agent / ecosystem surface

Goal: expose LogLens as a tool an LLM agent can call (note: the *agent* may be an LLM, but
LogLens itself runs no model here — these are thin, deterministic wrappers over the existing
API), plus the durability and I/O niceties a real package needs.

### ⚑ Decision gate V2.C — skill/tool format
Resolve before Phase V2.9:
- **Plain tool functions** — pure functions with JSON-serializable I/O + JSON schemas. Most
  portable; any agent framework can wrap them.
- **MCP server** — wrap the tool functions as a Model Context Protocol server.
- **Both** — functions as the core, MCP as an optional thin wrapper.

Recommendation: build the JSON tool-function core first (framework-agnostic), then an optional
MCP wrapper behind an extra.

### Phase V2.9 — Tool surface

#### Step V2.9.1 — tools.py
```
Create src/loglens/tools.py exposing a small set of agent-facing functions, each
taking and returning only JSON-serializable types (dicts/lists/str/num/bool):
- parse_logs(text) -> {"flows": [...]}  (flows as plain dicts)
- query_logs(text, query, top_k=10) -> {"results": [...]}  (requires the ai extra)
- find_gaps(text) -> {"annotations": [...]}
- check_expectations(text, rules_path) -> {"annotations": [...]}
Each function has a clear docstring and an accompanying JSON schema describing its
arguments. Add a TOOL_SCHEMAS dict mapping name -> schema. Keep these as thin
wrappers over the existing LogLens API — no new logic. (No summarize tool: V2 has
no LLM.)

Then tests/test_tools.py: assert every function returns JSON-serializable output
(json.dumps round-trips) and that each schema is valid JSON Schema. Run and fix
until green.
```
**Accept when:** all tool outputs JSON-serialize and schemas validate.

### Phase V2.10 — Persistence

#### Step V2.10.1 — durable template state
```
Add optional Drain3 file persistence so template ids stay stable across separate
runs/invocations (important when an agent calls the tools repeatedly). Extend
TemplateParser to accept a state_path; when set, use Drain3 FilePersistence to
load on start and save on update. Default remains in-memory (no file).

Then tests/test_persistence.py: parse some lines with a temp state_path, create a
NEW parser pointing at the same path, parse a matching line, assert it gets the
same template_id as the first run. Run and fix until green.
```
**Accept when:** template ids persist identically across a fresh parser on the same state file.

### Phase V2.11 — MCP wrapper (optional)

#### Step V2.11.1 — mcp_server.py
```
If decision gate V2.C chose MCP: create src/loglens/mcp_server.py behind a new
optional extra [mcp]. Lazy-import the MCP Python SDK (pin the current version in
pyproject), register the tools.py functions as MCP tools using TOOL_SCHEMAS, and
expose a `loglens-mcp` console script that starts the server. Keep it a thin
adapter — no business logic here.

Then a smoke test that imports the module only when the mcp extra is present
(pytest.importorskip). Run and fix until green.
```
**Accept when:** the server starts and lists the tools; skipped cleanly without the extra.

### Phase V2.12 — I/O niceties + machine output

#### Step V2.12.1 — sources & renderers
```
Add lightweight, stdlib-only conveniences:
- Ingestion: transparent .gz support and NDJSON files in the LogLens loader.
- Rendering: render_flows_json(flows) -> JSON for machine consumers, and an
  optional render_flows_mermaid(flows) -> a Mermaid flowchart string for the
  call/flow tree.
Wire CLI flags --json and --mermaid to select the renderer.

Then tests/test_io.py: a .gz fixture ingests correctly; render_flows_json
round-trips; render_flows_mermaid emits valid-looking Mermaid. Run and fix until
green.
```
**Accept when:** gz/NDJSON ingest, JSON and Mermaid renderers work.

---

## Phase V2.13 — Package & ship

#### Step V2.13.1 — README + version + tag
```
Update README.md with the new flags (--gaps, --expect, --lineage, --json,
--mermaid), the `loglens trace -m <module>` entry, the agent tool surface, and the
optional [mcp] extra. Bump version to 0.2.0. Final review of the tree for dead code
or stray files. Commit "chore: v0.2.0 release prep" and create git tag v0.2.0.
```
**Accept when:** README covers every new feature; clean tree, tagged v0.2.0.

---

## V2 layout additions

```
src/loglens/
├── gaps.py            # structural anomaly detectors          (Part A)
├── expectations.py    # declared YAML expectation rules        (Part A)
├── lineage.py         # follow one value across flows          (Part A)
├── tracer.py          # sys.setprofile call tracer             (Part B)
├── trace_to_flow.py   # CallEvent -> Flow                      (Part B)
├── tools.py           # agent-facing JSON tool functions       (Part C)
└── mcp_server.py      # optional MCP wrapper [mcp]             (Part C)
(parser.py, lens.py, render.py, cli.py extended)
tests: one focused file per new module + a trace integration test.
```

## Dependency summary

| Concern | Dependency | Where |
|---|---|---|
| Expectation rules | `PyYAML` | core (small) |
| Runtime tracer + JSON/Mermaid renderers | none | stdlib |
| Semantic query (V1, unchanged) | `sentence-transformers`, `rank-bm25` | `[ai]` extra |
| MCP server | MCP Python SDK | `[mcp]` extra |

The deterministic core never depends on a generative model. The `Flow` object stays the
single contract across logs *and* traces, which is what lets the renderer, gap detection,
and the agent tools serve both ingestion paths without change.
