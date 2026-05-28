# LogLens — Build Plan (V3: live runtime tracing)

Target tag: **v0.3.0**. Builds on V1 + V2. Same rules: lightweight, stdlib-first, `src/`
layout, test-gated, one focused test file per module. **No new runtime dependencies** — this
version is entirely standard library.

Goal: add a second *ingestion* mechanism — instrument running code, capture the call tree with
zero code changes, and emit it as the **same `Flow` object** so the existing renderer, gap
detection, and summarizer all work on it unchanged.

**Prime Claude Code first:**
```
Read DESIGN.md and the existing src/loglens code (V1 + V2 are done). We are now
building V3: a runtime call tracer that produces the SAME Flow object the log
pipeline produces, so render.py, gaps.py, and the summarizer work on traced flows
unchanged. Stdlib only — no new runtime dependencies. Same rules: lightweight,
src/ layout, focused tests per module. Do not write code yet — confirm you've read
the code and are ready for the first step.
```

---

### ⚑ Decision gate V3.A — tracing backend
Resolve before Phase V3.1:
- **`sys.setprofile`** — works on all supported versions (3.10+), simple API, higher overhead.
- **`sys.monitoring`** (PEP 669) — 3.12+ only, much lower overhead, slightly more API.

Recommendation: build the `sys.setprofile` backend first (portable across your 3.10+ target),
behind a backend seam so a `sys.monitoring` backend can be added later for 3.12+ users without
changing callers.

## Phase V3.1 — Tracer core

### Step V3.1.1 — tracer.py
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

## Phase V3.2 — Trace → Flow

### Step V3.2.1 — trace_to_flow.py
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

## Phase V3.3 — Concurrency honesty

### Step V3.3.1 — threads & async
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

## Phase V3.4 — Integration + guardrails

### Step V3.4.1 — wire tracing into the facade + CLI
```
Add to LogLens: a trace(include, capture_args=False) context manager that runs
user code under the Tracer and ingests the resulting flows into the same store as
logs, so show()/gaps()/summarize() all work over traced flows. Document a CLI
entry `loglens trace -m <module>` that imports and runs a module under the tracer
and prints the flow tree. Add a short README section stating tracing is for
dev/debug only (overhead) and that max_events bounds memory.

Then tests/test_trace_integration.py: trace a small callable via the context
manager and assert show() includes the traced flow. Bump version to 0.3.0,
commit, tag v0.3.0.
```
**Accept when:** code traced via the facade renders alongside logs; v0.3.0 tagged.

---

## V3 layout additions
```
src/loglens/tracer.py · trace_to_flow.py   (lens.py + cli.py extended)
tests: one per new module + an integration test.  No new runtime deps.
```

Next: `BUILD_PLAN_V4.md` (agent / ecosystem).
