# LogLens — Build Plan (V4: agent / ecosystem)

Target tag: **v0.4.0**. Builds on V1 + V2 + V3. Same rules: lightweight, stdlib-first, `src/`
layout, heavy deps behind optional extras, test-gated, one focused test file per module.

Goal: expose LogLens as a tool an LLM agent can call (the original dual-mode idea), plus the
durability and I/O niceties a real package needs.

**Prime Claude Code first:**
```
Read DESIGN.md and the existing src/loglens code (V1-V3 are done). We are now
building V4: an agent-facing tool surface plus persistence and I/O conveniences.
The tool functions are thin wrappers over the existing LogLens API — no new core
logic. Same rules: lightweight, src/ layout, heavy deps behind optional extras,
focused tests per module. Do not write code yet — confirm you've read the code and
are ready for the first step.
```

Decision gates marked ⚑ must be resolved before the steps beneath them.

---

### ⚑ Decision gate V4.A — skill/tool format
Resolve before Phase V4.1:
- **Plain tool functions** — pure functions with JSON-serializable I/O + JSON schemas. Most
  portable; any agent framework can wrap them.
- **MCP server** — wrap the tool functions as a Model Context Protocol server.
- **Both** — functions as the core, MCP as an optional thin wrapper.

Recommendation: build the JSON tool-function core first (framework-agnostic), then an optional
MCP wrapper behind an extra.

## Phase V4.1 — Tool surface

### Step V4.1.1 — tools.py
```
Create src/loglens/tools.py exposing a small set of agent-facing functions, each
taking and returning only JSON-serializable types (dicts/lists/str/num/bool):
- parse_logs(text) -> {"flows": [...]}  (flows as plain dicts)
- query_logs(text, query, top_k=10) -> {"results": [...]}
- find_gaps(text) -> {"annotations": [...]}
- summarize_flow(text, flow_id) -> {"summary": "..."}  (requires the llm extra)
Each function has a clear docstring and an accompanying JSON schema describing its
arguments. Add a TOOL_SCHEMAS dict mapping name -> schema. Keep these as thin
wrappers over the existing LogLens API — no new logic.

Then tests/test_tools.py: assert every function returns JSON-serializable output
(json.dumps round-trips) and that each schema is valid JSON Schema. Run and fix
until green.
```
**Accept when:** all tool outputs JSON-serialize and schemas validate.

## Phase V4.2 — Persistence

### Step V4.2.1 — durable template state
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

## Phase V4.3 — MCP wrapper (optional)

### Step V4.3.1 — mcp_server.py
```
If decision gate V4.A chose MCP: create src/loglens/mcp_server.py behind a new
optional extra [mcp]. Lazy-import the MCP Python SDK (pin the current version in
pyproject), register the tools.py functions as MCP tools using TOOL_SCHEMAS, and
expose a `loglens-mcp` console script that starts the server. Keep it a thin
adapter — no business logic here.

Then a smoke test that imports the module only when the mcp extra is present
(pytest.importorskip). Run and fix until green.
```
**Accept when:** the server starts and lists the tools; skipped cleanly without the extra.

## Phase V4.4 — I/O niceties + machine output

### Step V4.4.1 — sources & renderers
```
Add lightweight, stdlib-only conveniences:
- Ingestion: transparent .gz support and NDJSON files in the LogLens loader.
- Rendering: render_flows_json(flows) -> JSON for machine consumers, and an
  optional render_flows_mermaid(flows) -> a Mermaid flowchart string for the
  call/flow tree.
Wire CLI flags --json and --mermaid to select the renderer.

Then tests/test_io.py: a .gz fixture ingests correctly; render_flows_json
round-trips; render_flows_mermaid emits valid-looking Mermaid. Run and fix until
green. Bump version to 0.4.0, update README, commit, tag v0.4.0.
```
**Accept when:** gz/NDJSON ingest, JSON and Mermaid renderers work; v0.4.0 tagged.

---

## V4 layout additions
```
src/loglens/tools.py · mcp_server.py(optional)   (parser.py, lens.py, render.py,
cli.py extended)   tests: one per new module.
optional extra: [mcp]
```

---

## Roadmap summary (all versions)

| Version | Theme | New modules | New deps |
|---|---|---|---|
| **V1** | Deterministic core + semantic query | normalize, parser, correlate, models, render, analyzer, lens, cli | drain3 (+ `[ai]`) |
| **V2** | AI understanding layer | gaps, expectations, providers, lineage | yaml (+ `[llm]`) |
| **V3** | Live runtime tracing | tracer, trace_to_flow | none (stdlib) |
| **V4** | Agent / ecosystem | tools, mcp_server | (+ `[mcp]`) |

The deterministic core never depends on a model; every model or framework arrives as an
optional extra. The `Flow` object stays the single contract across logs *and* traces, which is
what lets the renderer, gap detection, and summarizer serve both ingestion paths without
change.
