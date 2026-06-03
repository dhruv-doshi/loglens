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
# Request/operation lifecycle endings — used by dangling_start. Broad on purpose:
# a flow that reaches ANY of these has not "dangled". Includes business-level
# completions like "confirmed"/"accepted" so successful flows aren't flagged.
TERMINAL_KEYWORDS = (
    "finished",
    "done",
    "sent",
    "completed",
    "complete",
    "closed",
    "failed",
    "error",
    "confirmed",
    "accepted",
    "acknowledged",
    "responded",
    "served",
    "rejected",
    "aborted",
    "cancelled",
    "canceled",
)
EXCEPTION_SIGNATURES = (
    "traceback",
    "exception",
    "error:",
    " at ",
    "caught ",
    "stack trace",
)
# CamelCase exception/fault class names (e.g. PaymentGatewayTimeout), which a
# swallowed error often logs without any of the literal signatures above.
_EXCEPTION_NAME_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Timeout|Failure|Fault)\b"
)
# Words showing a RETRIED operation actually reached an outcome (success or a
# definitive give-up/failure), so the retry is resolved. Deliberately excludes
# vague flow-level terminals like "confirmed"/"sent" that don't speak to whether
# the retried operation itself succeeded — that gap is the architect's to judge.
RETRY_RESOLUTION_KEYWORDS = (
    "success",
    "succeeded",
    "recovered",
    "resolved",
    "completed",
    "complete",
    "established",
    "connected",
    "accepted",
    "ok",
    "gave up",
    "giving up",
    "abandon",
    "aborted",
    "abort",
    "failed",
    "failure",
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
        hay = _haystack(r)
        if not (_has_any(hay, EXCEPTION_SIGNATURES) or _EXCEPTION_NAME_RE.search(hay)):
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
            _has_any(_msg(x), RETRY_RESOLUTION_KEYWORDS) for x in later
        )
        if not resolved:
            out.append(
                Annotation(
                    flow.flow_id,
                    r.seq,
                    "unresolved_retry",
                    f"retry '{text.strip()}' has no later success or give-up",
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
