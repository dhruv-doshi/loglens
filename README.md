# LogLens

Turn mixed-format logs into a readable reconstruction of execution flow. LogLens
normalizes JSON, logfmt, syslog-ish, and free-text lines into one schema, mines
templates, groups events into flows by correlation ID (with a best-effort
fallback), and renders the result so an architect can see what the code actually
did — and where it quietly didn't do what it should.

Offline, small footprint, stdlib-first. Runtime dependencies are
[`drain3`](https://pypi.org/project/drain3/) and `PyYAML`. Everything model-based
or framework-specific is an opt-in extra. LogLens runs **no generative LLM** — its
analysis (gap detection, expectation rules) is deterministic and explainable.

## Install

```
pip install loglens
```

Optional extras:

```
pip install loglens[ai]    # offline semantic query (sentence-transformers + rank-bm25)
pip install loglens[mcp]   # expose the tools over a Model Context Protocol server
```

## What's in V2

Built on the deterministic V1 core (normalize → template-mine → correlate →
render), V2 adds, all without an LLM:

- **Gap & anomaly detection** — dangling starts, exceptions logged below `ERROR`,
  unresolved retries.
- **Declared expectation rules** — a tiny YAML "after X expect one of Y" check.
- **Lineage** — follow one value (order id, user id) across every flow.
- **Runtime call tracer** — instrument running code via `sys.setprofile` and emit
  the *same* `Flow` object, so the renderer and gap detection work on traces too.
- **Agent tool surface** — JSON-in/JSON-out functions (+ optional MCP server).
- **Machine output** — JSON and Mermaid renderers; transparent `.gz`/NDJSON ingest.

## Library usage

```python
from loglens import LogLens

lens = LogLens()
lens.ingest("app.log")                  # path, open file, or iterable of lines
print(lens.show())                      # rendered flow view

for record, score in lens.query("connection refused", top_k=5):
    print(f"{score:.3f}  {record.raw}")
```

`lens.flows()` returns a `list[Flow]` if you want the structured object instead
of rendered text.

### Understanding a flow

```python
lens = LogLens()
lens.ingest("app.log")

for flow_id, annotations in lens.gaps().items():       # structural anomalies
    for a in annotations:
        print(flow_id, a.kind, a.detail)

lens.check_expectations("rules.yaml")                   # declared expectations
lens.lineage("ORD-42")                                  # follow one value
```

### Tracing running code

```python
lens = LogLens()
with lens.trace(include=["/path/to/your/package"]):     # dev/debug only — overhead
    run_your_code()
print(lens.show())                                      # traced flows render like logs
```

### Agent tools

```python
from loglens import tools

tools.parse_logs(text)                  # {"flows": [...]}
tools.find_gaps(text)                   # {"annotations": [...]}
tools.check_expectations(text, "rules.yaml")
tools.TOOL_SCHEMAS                       # JSON Schema per tool
```

With the `[mcp]` extra installed, the same tools are served over the Model Context
Protocol — start the server with the `loglens-mcp` console script.

### Stable template ids across runs

Template ids are in-memory by default. Pass a `state_path` to persist Drain3's
learned templates so ids stay stable across separate runs (useful when an agent
calls the tools repeatedly):

```python
from loglens.parser import TemplateParser

lens = LogLens()
lens.parser = TemplateParser(state_path="loglens.state")
```

## `logging.Handler` middleware

Capture live logs from a running program into the same flow view:

```python
import logging
from loglens import LogLens, LogLensHandler

lens = LogLens()
logging.getLogger().addHandler(LogLensHandler(lens))
logging.getLogger().setLevel(logging.INFO)

# ... your application runs and emits logs ...

print(lens.show())
```

The handler reads structured fields directly from `logging.LogRecord` — no
string-format roundtrip — so level, source, and timestamps stay clean.

## CLI

```
loglens app.log                              # print grouped flow view
loglens app.log --query "timeout" --top-k 5  # rank lines by relevance (needs [ai])
loglens app.log --gaps                        # show structural anomalies per flow
loglens app.log --expect rules.yaml           # check declared expectation rules
loglens app.log --lineage ORD-42              # follow one value across flows
loglens app.log --json                        # machine-readable JSON
loglens app.log --mermaid                     # Mermaid flowchart
loglens app.log --no-template                # show raw messages instead of mined templates
loglens app.log --color | less -R            # force color when piping
loglens trace -m your.module                  # trace a module's call tree as flows
loglens --version
```

`.gz` files are ingested transparently. Without the `[ai]` extra installed,
`--query` exits non-zero with the install hint.

## Try it on sample logs

`samples/` ships with four real-world shapes — nginx access, Kubernetes pod
stdout, Django/Python logging, and a mixed-format checkout incident — so you can
see what loglens does without hunting for a log file:

```
loglens samples/nginx-access.log
loglens samples/k8s-pod.log
loglens samples/django-app.log
loglens samples/checkout-incident.log
```

The checkout incident interleaves JSON, logfmt, syslog and Python logging across
several requests. Point the analysis at it:

```
loglens samples/checkout-incident.log --gaps
#   req-7f3a: 2 unresolved retries + a PaymentGatewayTimeout swallowed at INFO
#   (the successful checkout req-9c21 stays clean)

loglens samples/checkout-incident.log --lineage req-7f3a   # one request, every service
```

## How it works

Six layers: ingestion → normalization → template mining (Drain3) → correlation
(4-tier ID cascade) → analysis → presentation. Layers 1–4 are a deterministic,
model-free core that emits a structured `Flow` object; everything downstream
consumes that object. The runtime tracer is a second ingestion path that emits the
*same* `Flow`, so the renderer, gap detection, and agent tools all serve logs and
traces without change. Embeddings only power the optional semantic query — flow
reconstruction and analysis need no model.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full architecture and rationale.

## License

MIT.
