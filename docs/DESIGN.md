# LogLens — Design Doc

> Working name. A pip-installable Python package that turns mixed-format logs into a
> readable reconstruction of execution flow, so a software architect can see what the
> code actually did — and where it quietly didn't do what it should.

---

## 1. Problem

AI-generated (and human) code often works on the happy path but takes silent shortcuts:
a critical check that should raise is swallowed, an error is downgraded to `INFO`, a
branch is skipped. Logs contain the evidence, but they're noisy, mixed-format, and
interleaved. An architect needs the *flow* made legible — what ran, in what order,
grouped by request — so they can draw conclusions themselves.

## 2. Goals / Non-goals

**Goals**
- Parse arbitrary mixed-format logs (JSON, logfmt, syslog-ish, free text) into one schema.
- Reconstruct and group events into flows by correlation ID (or a best-effort fallback).
- Render the flow so a human can read it and reason about it.
- Offline-first, small footprint, pip-installable.
- Architecture where AI features and live tracing are *additive*, not rewrites.

**Non-goals (V1)**
- No automated judgement of "what went wrong" — the architect decides.
- No gap/anomaly rules, no required configuration.
- No cloud dependency.

## 3. Architecture

Six layers. Layers 1–4 are a deterministic core that emits a structured `Flow` object;
everything downstream (renderers, AI, the future tracer) consumes that object.

```
1. Ingestion        file · stream · logging.Handler middleware
2. Normalization    json → logfmt → regex → raw fallback   →  LogRecord
3. Template mining   Drain3: assign template_id, dedup variants
4. Enrichment        correlation (ID cascade), ordering      →  Flow graph
5. Analysis          relevance query · (later) AI summary · (later) gap rules
6. Presentation      presets render the same Flow graph (CLI + library)
```

The renderer takes an opt-in `color` flag and emits ANSI escapes only when asked
(stdlib only, no `rich`/`colorama`). The CLI auto-enables color when stdout is a
TTY and `NO_COLOR` is unset; `--color` / `--no-color` force the choice. Levels,
template placeholders, flow IDs, sources, and timestamps each get a distinct
treatment so an architect's eye can find the warns and errors without reading
every line. The library API (`lens.show()` / `render_flows()`) defaults
`color=False` so structured callers and tests get plain text.

**Core principle:** the deterministic core is model-free and explainable. The embedding
model only powers the semantic query; flow reconstruction needs no model at all.

### Data model (the seam)

```python
@dataclass
class LogRecord:
    ts: datetime | None
    level: str | None
    source: str | None
    message: str            # free text → Drain3
    template_id: str | None
    template: str | None
    flow_id: str            # resolved or synthesized
    flow_origin: str        # "field:trace_id" | "regex" | "synthesized"
    seq: int                # stream order, tiebreaker
    raw: str                # original line, always kept
    fields: dict

@dataclass
class Flow:
    flow_id: str
    origin: str
    records: list[LogRecord]   # ordered
    # renderers and AI analyzers consume Flow, never raw text
```

`Flow` is the contract. As long as V1 emits it cleanly, every later feature attaches
without touching normalize / correlate / parse.

## 4. Key design decisions

| Decision | Choice | Why |
|---|---|---|
| Template mining | Depend on `drain3` (PyPI), don't fork | MIT, stable, exposes the API we need |
| Correlation | Deterministic 4-tier ID cascade, no ML | IDs/time group reliably; embeddings merge unrelated flows |
| Embedding backend | `sentence-transformers` first, swap to ONNX before publish | ONNX is ~10× lighter (~120 MB vs ~1–2 GB) |
| GPU | Never required | torch CPU + onnxruntime are CPU-only by default |
| AI provider | Behind a provider-agnostic `Analyzer` interface | Local-vs-API stays a late decision |
| Offline | Default for all V1/V2 local features | Stated requirement |

### Correlation cascade (the heart of V1)

1. Configured ID field (explicit).
2. Auto-detected ID field (`trace_id`, `request_id`, `correlation_id`, `session_id`, …).
3. ID extracted from message body via regex (UUID / hex / `req=…`).
4. Synthesized: thread/PID + time-gap windowing → readable handle `flow-0001`.
   Labeled "best effort" — concurrent ID-less flows can interleave and cannot be
   reliably separated. The output is honest about which tier produced each grouping.

## 5. Versioned feature list

### V1 — Core flow legibility (the ~2-hour ship)
- Normalization cascade → `LogRecord`.
- Drain3 template mining + dedup.
- 4-tier correlation cascade → `Flow`.
- Flow renderer: ordered, grouped, collapsed-by-template tree (CLI text + structured object).
- Library API (`LogLens.ingest()`, `.flows()`, `.show()`) + `logging.Handler` middleware + CLI.
- **Offline semantic error query** — embeddings + cosine, hybrid with BM25 for literal
  error strings. The one AI feature in V1; self-contained and offline.
- Deps: `drain3` + an embedding backend. Stdlib otherwise.

### V2 — AI understanding layer
- **Flow summarization** — LLM over a `Flow`: "summarize what happened, flag anything
  skipped or swallowed." Provider-agnostic (`Analyzer.summarize(flow)`); decision pending
  on offline local LLM vs API.
- **Gap / anomaly surfacing** — structural heuristics (dangling start with no
  finish/fail, exception logged below `ERROR`, unresolved retries) + optional declared
  expectation rules (lightweight YAML state machine).
- Additional preset: `lineage` (follow one value across the flow).

### V3 — Live runtime tracing (the "epic")
- **Auto function-call tracer** — `sys.monitoring` (3.12+) / `sys.setprofile`, filtered
  to the user's package, builds a call tree with zero code changes.
- Tree maps onto the **same `Flow` object** → existing renderer + AI work for free.
- A second *ingestion* mechanism (generates its own trace) feeding the same downstream.
- Caveats to handle: per-thread registration, async interleaving, opt-in/truncated arg
  capture, dev-only overhead.
- No new dependencies (stdlib).

### V4 — Agent / ecosystem
- **LLM skill mode** — thin wrapper exposing parse/filter/summarize as a tool agents call.
- Persistence (Drain3 state across runs), more ingestion sources, richer renderers.

## 6. Test strategy

- **Normalization:** one case per format branch + a garbage line that must not crash.
- **Correlation:** asserts each tier fires correctly; synthesized flows labeled honestly.
- **Template mining:** variants collapse to one `template_id`; distinct messages don't collide.
- **Relevance (V1 AI):** known-relevant line lands in top-k (assert ordering, not float scores).
- **Robustness:** malformed lines never raise; large files stream without loading wholesale.
- Tune the correlation candidate list and synthesis threshold against **real log samples**,
  not synthetic ones.

## 7. Open decisions

- Package name (`loglens` is a placeholder).
- Embedding model: `all-MiniLM-L6-v2` vs `bge-small-en-v1.5`.
- V2 summarization provider: offline local LLM (heavier setup) vs API (online, needs key).
