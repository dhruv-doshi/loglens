# LogLens

Turn mixed-format logs into a readable reconstruction of execution flow. LogLens
normalizes JSON, logfmt, syslog-ish, and free-text lines into one schema, mines
templates, groups events into flows by correlation ID (with a best-effort
fallback), and renders the result so an architect can see what the code actually
did — and where it quietly didn't do what it should.

Offline, small footprint, stdlib-first. The only runtime dependency is
[`drain3`](https://pypi.org/project/drain3/). Semantic query is an opt-in extra.

## Install

```
pip install loglens
```

Optional offline semantic error query (adds `sentence-transformers` + `rank-bm25`):

```
pip install loglens[ai]
```

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
```

Without the `[ai]` extra installed, `--query` exits non-zero with the install
hint.

## How it works

Six layers: ingestion → normalization → template mining (Drain3) → correlation
(4-tier ID cascade) → analysis → presentation. Layers 1–4 are a deterministic,
model-free core that emits a structured `Flow` object; everything downstream
consumes that object. Embeddings only power the optional semantic query — flow
reconstruction needs no model.

See [`DESIGN.md`](DESIGN.md) for the full architecture and rationale.

## License

MIT.
