from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Flow, LogRecord

# Keyword lists live at module top, case-insensitive, easy to extend.
ENTRY_KEYWORDS = (
    "started",
    "starting",
    "begin",
    "beginning",
    "received",
    "entering",
    "opening",
)
TERMINAL_KEYWORDS = (
    "finished",
    "done",
    "sent",
    "completed",
    "complete",
    "closed",
    "failed",
    "error",
)
EXCEPTION_SIGNATURES = (
    "traceback",
    "exception",
    "error:",
    " at ",
)
SUCCESS_KEYWORDS = (
    "success",
    "succeeded",
    "completed",
    "complete",
    "done",
    "finished",
    "sent",
    "resolved",
    "ok",
)
RETRY_RE = re.compile(r"\b(?:retry|retrying|attempt\s+\d+)\b", re.IGNORECASE)

# logging-style numeric ranks; anything below ERROR (40) is a "downgrade".
_ERROR_RANK = 40
_LEVEL_RANK = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "NOTICE": 25,
    "WARN": 30,
    "WARNING": 30,
    "ERR": 40,
    "ERROR": 40,
    "FATAL": 50,
    "CRITICAL": 50,
}


@dataclass
class Annotation:
    flow_id: str
    record_seq: int
    kind: str
    detail: str


def _msg(r: LogRecord) -> str:
    return r.template or r.message or ""


def _haystack(r: LogRecord) -> str:
    parts = [r.message or "", r.template or ""]
    parts.extend(str(v) for v in r.fields.values())
    return " ".join(parts)


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(k in low for k in keywords)


def _level_rank(level: str | None) -> int | None:
    if level is None:
        return None
    return _LEVEL_RANK.get(level.strip().upper())


def _dangling_starts(flow: Flow) -> list[Annotation]:
    out: list[Annotation] = []
    recs = flow.records
    for i, r in enumerate(recs):
        text = _msg(r)
        if not _has_any(text, ENTRY_KEYWORDS):
            continue
        if not any(_has_any(_msg(x), TERMINAL_KEYWORDS) for x in recs[i + 1 :]):
            out.append(
                Annotation(
                    flow.flow_id,
                    r.seq,
                    "dangling_start",
                    f"entry event '{text.strip()}' has no matching terminal event",
                )
            )
    return out


def _downgraded_errors(flow: Flow) -> list[Annotation]:
    out: list[Annotation] = []
    for r in flow.records:
        if not _has_any(_haystack(r), EXCEPTION_SIGNATURES):
            continue
        rank = _level_rank(r.level)
        if rank is not None and rank < _ERROR_RANK:
            out.append(
                Annotation(
                    flow.flow_id,
                    r.seq,
                    "downgraded_error",
                    f"exception signature logged at level {r.level} (below ERROR)",
                )
            )
    return out


def _unresolved_retries(flow: Flow) -> list[Annotation]:
    out: list[Annotation] = []
    recs = flow.records
    for i, r in enumerate(recs):
        text = _msg(r)
        if not RETRY_RE.search(text):
            continue
        later = recs[i + 1 :]
        resolved = any(
            _has_any(_msg(x), SUCCESS_KEYWORDS) or _has_any(_msg(x), TERMINAL_KEYWORDS)
            for x in later
        )
        if not resolved:
            out.append(
                Annotation(
                    flow.flow_id,
                    r.seq,
                    "unresolved_retry",
                    f"retry '{text.strip()}' has no later success or terminal event",
                )
            )
    return out


def detect_gaps(flow: Flow) -> list[Annotation]:
    """Surface structural anomalies in a flow. Deterministic, no I/O."""
    annotations: list[Annotation] = []
    annotations.extend(_dangling_starts(flow))
    annotations.extend(_downgraded_errors(flow))
    annotations.extend(_unresolved_retries(flow))
    annotations.sort(key=lambda a: (a.record_seq, a.kind))
    return annotations
