# LogLens — Build Plan (V1)

A step-by-step plan to build the V1 package from `DESIGN.md` using the Claude Code CLI.
Each **step** is a self-contained prompt — quote it verbatim into Claude Code, review the
output, accept, then move on. Build is test-gated: most steps end with "write tests, run
them, fix until green."

**Principles enforced throughout:** lightweight, stdlib-first (argparse not click,
dataclasses not pydantic), `src/` layout, AI deps optional, no speculative code.

**Before you start:** put `DESIGN.md` in the repo root so Claude Code can read it.

---

## Phase 0 — Repo, packaging, tooling

### Step 0.1 — Prime Claude Code
```
Read DESIGN.md in this repo. We are building the V1 package described there, in
this Claude Code session, one module at a time. I will paste each step as a
separate instruction. Follow these rules for everything you write:
- Python 3.10+, src/ layout, package name "loglens".
- Lightweight and minimal: prefer the standard library. No dependency unless it
  earns its place. The only hard runtime dependency is drain3.
- Type-hinted, small functions, no speculative abstractions, no dead code.
- Every code module gets a matching pytest file. After writing a module, run its
  tests and fix until green before stopping.
Do not write any code yet. Confirm you've read DESIGN.md and are ready for step 1.
```
**Accept when:** it confirms it read the doc and is waiting.

### Step 0.2 — Scaffold + packaging
```
Create the project scaffold:
- src/loglens/__init__.py  (exposes __version__ = "0.1.0")
- tests/  (empty, with __init__.py if needed)
- pyproject.toml using the hatchling build backend, PEP 621 metadata, name
  "loglens", version 0.1.0, requires-python ">=3.10".
  dependencies = ["drain3>=0.9.11"]
  optional-dependencies: ai = ["sentence-transformers>=2.2", "rank-bm25>=0.2"];
  dev = ["pytest>=7"]
  A console script entry point: loglens = "loglens.cli:main"
  Configure hatch to package src/loglens.
- A standard Python .gitignore, an MIT LICENSE, and a minimal README.md stub.
Do not implement cli.py yet — just the packaging so the entry point resolves later.
```
**Accept when:** files exist and `pyproject.toml` is valid.

### Step 0.3 — Environment + first commit
```
Create a venv, install the package editable with dev extras
(pip install -e ".[dev]"), confirm `python -c "import loglens"` works and
`pytest` runs (zero tests is fine). Then: git init, add everything, and make the
first commit "chore: scaffold loglens package".
```
**Accept when:** import works, pytest runs clean, first commit exists.

---

## Phase 1 — Data model (the contract)

### Step 1.1 — models.py
```
Create src/loglens/models.py with two dataclasses and one helper, matching the
data model in DESIGN.md:

- LogRecord: ts (datetime|None), level (str|None), source (str|None),
  message (str), template_id (str|None), template (str|None), flow_id (str),
  flow_origin (str), seq (int), raw (str), fields (dict). Give the
  later-filled fields sensible defaults ("" / None).

- Flow: flow_id (str), origin (str), records (list[LogRecord]). Add read-only
  properties: start_ts, end_ts, duration (timedelta|None), event_count.

- build_flows(records: list[LogRecord]) -> list[Flow]: group records by flow_id,
  sort each group by (ts or datetime.min, seq), return Flows sorted by start_ts.

Then write tests/test_models.py covering build_flows grouping, ordering by seq
when timestamps tie, and the Flow properties. Run and fix until green.
```
**Accept when:** `test_models.py` is green.

---

## Phase 2 — Normalization

### Step 2.1 — normalize.py
```
Create src/loglens/normalize.py. One public function:
  normalize_line(raw: str, seq: int) -> LogRecord

Implement a cascade, stdlib only (json, re, datetime). Stop at the first that
parses:
1. JSON object -> map ts/level/msg/message/logger/source keys; everything else
   into fields.
2. logfmt (key=value pairs, quoted values allowed) -> same mapping.
3. Regex for common shapes: ISO-8601 timestamp + level + message; classic syslog
   (Mon DD HH:MM:SS host proc: msg).
4. Fallback: whole line becomes message; still try to sniff a leading timestamp
   and an uppercase level token.

Add a small internal timestamp parser for the few common formats (ISO-8601 with
optional Z/offset, syslog "%b %d %H:%M:%S"). No external date libraries. Leave
template_id/template/flow_id/flow_origin unset (defaults). Preserve raw.

Then tests/test_normalize.py with one line per branch (a JSON line, a logfmt
line, an ISO line, a syslog line) plus a garbage line that must NOT raise and
must land in message. Run and fix until green.
```
**Accept when:** every branch maps correctly and garbage never raises.

---

## Phase 3 — Template mining

### Step 3.1 — parser.py
```
Create src/loglens/parser.py wrapping drain3. A class TemplateParser:
- __init__ builds a TemplateMinerConfig in code (no .ini, no persistence for V1),
  with masking for IP, NUM, UUID, and HEX. Construct a TemplateMiner from it.
- assign(record: LogRecord) -> LogRecord: feed record.message to
  add_log_message, set record.template_id = f"T{cluster_id:04d}" and
  record.template = the mined template. Return the record.

Keep it tiny. Then tests/test_parser.py: feed several variants of the same
message (differing only in numbers/IPs) and assert they collapse to one
template_id; assert two clearly different messages get different ids. Run and fix
until green.
```
**Accept when:** variants collapse, distinct messages don't collide.

---

## Phase 4 — Correlation (the heart)

### Step 4.1 — correlate.py
```
Create src/loglens/correlate.py implementing the 4-tier cascade from DESIGN.md.
A class Correlator:
- __init__(id_fields: list[str] | None = None, time_gap_seconds: float = 5.0).
  Default id_fields: trace_id, traceId, request_id, requestId, req_id,
  correlation_id, correlationId, span_id, session_id, txn_id, id.
- resolve(records: list[LogRecord]) -> None  (mutates in place): for each record
  assign flow_id and flow_origin using, in order:
    1. a configured/auto-detected id field present in record.fields
       -> origin "field:<name>"
    2. an id extracted from record.message by regex (UUID, long hex >=8,
       or key=value where key looks like an id) -> origin "regex"
    3. synthesized: group by (source, thread/pid if present) and start a new
       flow when the gap since the last record in that group exceeds
       time_gap_seconds; handles like "flow-0001"; origin
       "synthesized" (best effort).

Keep regexes precompiled at module level. Then tests/test_correlate.py: a set
with an explicit id field (tier 1), a set with ids only in the message (tier 2),
and an id-less set that must split into two synthesized flows across a time gap.
Assert flow_id grouping and flow_origin labels. Run and fix until green.
```
**Accept when:** all three tiers assign correctly and origins are labeled honestly.

---

## Phase 5 — Rendering

### Step 5.1 — render.py
```
Create src/loglens/render.py. One public function:
  render_flows(flows: list[Flow]) -> str

Pure string output, no dependencies, no color. For each flow print a header line:
  "<flow_id>  (origin: <origin>)  ·  <n> events  ·  <duration>"
then an indented tree of its records: "  ts  LEVEL  source  template-or-message".
Collapse runs of the same consecutive template_id into one line with " ×<count>".
Handle missing ts/level/duration gracefully.

Then tests/test_render.py: build a couple of Flows by hand and assert the header
format, the collapsing, and that None fields don't crash. Run and fix until green.
```
**Accept when:** output matches the format in DESIGN.md §"What the architect sees".

---

## Phase 6 — Facade, middleware, CLI

### Step 6.1 — lens.py (facade + middleware)
```
Create src/loglens/lens.py.

Class LogLens:
- __init__ holds a TemplateParser and a Correlator and an internal list of
  LogRecord plus a seq counter.
- ingest(source): accept an iterable of lines OR a file path OR an open file;
  for each line call normalize_line, then parser.assign; store records.
- flows() -> list[Flow]: run correlator.resolve over stored records, then
  build_flows. (Correlation runs at read time so it sees the whole batch.)
- show() -> str: render_flows(self.flows()).
- query(text, top_k=10): lazy-import the analyzer (Phase 7) and delegate; if the
  ai extra is missing, raise a clear error telling the user to
  `pip install loglens[ai]`.

Class LogLensHandler(logging.Handler): formats each LogRecord to a line and feeds
it into a LogLens instance passed to __init__ (incremental ingest).

Then tests/test_lens.py: ingest a small mixed-format list end-to-end and assert
flows() returns sensibly grouped Flows; test the handler captures emitted logs.
Run and fix until green.
```
**Accept when:** end-to-end ingest works and the handler captures live logs.

### Step 6.2 — cli.py
```
Create src/loglens/cli.py using argparse only. main():
- positional: logfile (path)
- optional: --query TEXT (run semantic query instead of the flow view),
  --top-k N (default 10)
- default behavior: load the file into a LogLens and print show().
- with --query: print ranked query results; if the ai extra is missing, print
  the install hint and exit non-zero cleanly.
Wire it to the console_scripts entry point. Keep it under ~40 lines.

Then a quick test: run `loglens <a sample file>` on a tiny fixture and confirm it
prints flows. Commit phases 1-6 as "feat: deterministic core + flow rendering".
```
**Accept when:** `loglens sample.log` prints grouped flows.

---

## Phase 7 — Semantic error query (optional AI feature)

### Step 7.1 — analyzer.py
```
Create src/loglens/analyzer.py.

- Define an Analyzer Protocol with: query(records, text, top_k) -> list of
  (LogRecord, score) ranked desc. (Leave room for a future summarize(flow) but
  do NOT implement it now.)
- Implement EmbeddingQuery(Analyzer): lazy-import sentence-transformers and
  rank_bm25 inside __init__ (so the base package never imports torch); raise a
  clear ImportError->RuntimeError with the `pip install loglens[ai]` hint if
  missing. Default model "sentence-transformers/all-MiniLM-L6-v2".
- query(): dedup records by template_id, embed unique templates once, embed the
  query text, score each unique template with
  score = 0.7 * cosine + 0.3 * normalized_bm25, map back to records, return
  top_k with scores.

Then tests/test_analyzer.py guarded with
`pytest.importorskip("sentence_transformers")`: a small corpus where a known
line must appear in the top results for a matching query. Assert membership/
ordering, never exact float values. Run and fix until green (skipped if extra
absent is acceptable).
```
**Accept when:** with `[ai]` installed, the relevant line ranks in the top-k.

### Step 7.2 — wire query in
```
Wire EmbeddingQuery into LogLens.query() and the CLI --query path. Confirm
`loglens sample.log --query "connection refused"` returns ranked lines, and that
running it WITHOUT the ai extra prints the install hint and exits cleanly.
Commit as "feat: optional offline semantic error query".
```
**Accept when:** query works with the extra, degrades gracefully without it.

---

## Phase 8 — Package & ship

### Step 8.1 — README + usage
```
Write README.md: one-paragraph what/why, install (`pip install loglens` and
`pip install loglens[ai]`), a library example (ingest a file, print show(),
run query()), the logging.Handler middleware example, and the CLI usage. Keep it
tight. Add a short "How it works" linking to DESIGN.md.
```
**Accept when:** a new reader could install and use it from the README alone.

### Step 8.2 — Build + verify in a clean env
```
Add "build" to dev deps if needed. Run `python -m build` to produce wheel +
sdist. Create a fresh throwaway venv, install ONLY the built wheel (no extra),
confirm `import loglens` and the CLI flow view work with zero heavy deps. Then
install the wheel with [ai] and confirm query works. Report sizes of both installs.
```
**Accept when:** base install is light (drain3 only) and AI install adds embeddings.

### Step 8.3 — Tag + (optional) publish
```
Final review of the tree for dead code or stray files; remove anything
unnecessary. Commit "chore: v0.1.0 release prep" and create git tag v0.1.0.
(Optional, only if I ask:) walk me through publishing to TestPyPI with twine
before the real PyPI.
```
**Accept when:** clean tree, tagged v0.1.0.

---

## Phase 9 — Post-release polish

Added after v0.1.0 shipped, in response to real-log feedback.

### Step 9.1 — Mixed tz-aware/naive timestamps (v0.1.1)
```
Real logs interleave ISO-8601 (tz-aware) and syslog/missing (naive) timestamps.
`build_flows` and `Correlator.resolve` sorted on `r.ts or datetime.min`, which
Python refuses to compare across awareness. Add a shared `_sortable()` helper
in models.py that coerces aware datetimes to tz-naive UTC for sort-key purposes
only; stored `ts` keeps its original tzinfo. Add a regression test mixing both.
```
**Accept when:** ingesting a log with both ISO-Z and syslog timestamps doesn't raise.

### Step 9.2 — ANSI color in CLI (v0.1.2)
```
Add `src/loglens/colors.py` with ANSI escape constants, a level→color map,
and `should_color(stream)` honoring `NO_COLOR` and TTY detection. Update
`render_flows(flows, *, color: bool = False)` to paint flow IDs (cyan+bold),
origins/timestamps/template-placeholders (dim), sources (magenta), and levels
(green INFO, yellow WARN, red ERROR/FATAL). Library default stays `color=False`
so callers and tests get plain text. CLI adds mutually exclusive `--color` /
`--no-color`, falling back to `should_color(sys.stdout)`. No new runtime deps —
stdlib ANSI only, per the "no `rich`/`colorama`" principle.
```
**Accept when:** `loglens file.log` in a TTY shows colored levels and dim
placeholders; piping output or setting `NO_COLOR=1` yields plain text;
`render_flows(flows)` (no kwarg) still returns plain text.

### Step 9.3 — Color the --query output too (v0.1.3)
```
Phase 9.2 only painted the flow view. The CLI `--query` path still printed
`f"{score}\t{record.raw}"` — uncolored raw lines. Expose a small
`format_query_result(record, score, *, color)` helper from `render.py` that
reuses the flow-row formatter (dim ts, level palette, magenta source,
template-placeholder dimming) and prefixes a dim score. Wire it into
`cli.py`'s query branch so query output follows the same color rules as the
flow view.
```
**Accept when:** `loglens file.log --query "..."` in a TTY shows colored
score + level + source + message; piping or `--no-color` yields plain text.

### Step 9.4 — Real-log polish (v0.1.4)
```
Run loglens against three realistic samples (nginx Combined Log Format,
k8s CRI container stdout, Django/Python logging) and fix every bug the
shakedown surfaces. New normalize.py branches:
  - Kubernetes CRI prefix `<rfc3339> (stdout|stderr) [FP] <inner>` is
    stripped before the cascade, then the inner payload is re-normalized
    so JSON / fields / level survive intact.
  - Python logging default `[YYYY-MM-DD HH:MM:SS,ms] LEVEL logger: msg`
    parsed as a first-class shape; `_parse_ts` learns comma-millis and
    the Apache `%d/%b/%Y:%H:%M:%S %z` format.
  - Apache/nginx Combined Log Format mapped: request → message,
    host → source, status code → level via 5xx=ERROR / 4xx=WARN / 2xx=INFO.
  - LogLens.ingest folds Python tracebacks into the preceding record using
    is_continuation() — indented lines, the "Traceback (most recent call
    last):" header, and "<dotted.path>ExceptionClass: msg" tails all merge,
    so a 500 error stays attached to its stack trace instead of fanning out
    into orphan flows.
Also: default id_fields gain `job_id`/`jobId`/`task_id`/`taskId` for worker
logs. CLI gains `--version` and `--no-template` (raw message view). Bundle
three example logs under samples/ so users can `loglens samples/k8s-pod.log`
out of the box.
```
**Accept when:** running loglens on each of samples/nginx-access.log,
samples/k8s-pod.log, samples/django-app.log yields readable flows with
correct timestamps, levels, sources, and (for django) the traceback folded
into its ERROR record.

---

## Final V1 layout (target)

```
loglens/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── LICENSE
├── .gitignore
├── src/loglens/
│   ├── __init__.py
│   ├── models.py      # LogRecord, Flow, build_flows
│   ├── normalize.py   # format cascade
│   ├── parser.py      # Drain3 wrapper
│   ├── correlate.py   # 4-tier ID cascade
│   ├── render.py      # flow → text tree
│   ├── colors.py      # ANSI palette + TTY/NO_COLOR detection (v0.1.2)
│   ├── analyzer.py    # optional semantic query
│   ├── lens.py        # LogLens facade + logging.Handler
│   └── cli.py         # argparse entry point
└── tests/             # one file per module
```

Nine code modules, one test file each. Base runtime dependency: `drain3`.
Everything else is standard library or an opt-in extra.
