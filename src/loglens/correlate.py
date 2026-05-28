from __future__ import annotations

import re
from datetime import datetime

from .models import LogRecord, _sortable

_DEFAULT_ID_FIELDS = [
    "trace_id", "traceId",
    "request_id", "requestId", "req_id",
    "correlation_id", "correlationId",
    "span_id",
    "session_id",
    "txn_id",
    "id",
]

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_KV_ID_RE = re.compile(
    r"\b(?:trace|traceId|request|requestId|req|correlation|correlationId|span|session|txn|id)"
    r"[_-]?id?\s*[=:]\s*([A-Za-z0-9._-]{4,})",
    re.IGNORECASE,
)
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")

_THREAD_KEYS = ("thread", "thread_id", "threadId", "tid", "pid")


def _thread_of(record: LogRecord) -> str | None:
    for k in _THREAD_KEYS:
        if k in record.fields:
            return f"{k}={record.fields[k]}"
    return None


class Correlator:
    def __init__(
        self,
        id_fields: list[str] | None = None,
        time_gap_seconds: float = 5.0,
    ) -> None:
        self.id_fields = list(id_fields) if id_fields else list(_DEFAULT_ID_FIELDS)
        self.time_gap_seconds = time_gap_seconds

    def _tier1(self, record: LogRecord) -> tuple[str, str] | None:
        for name in self.id_fields:
            if name in record.fields:
                val = record.fields[name]
                if val is None or val == "":
                    continue
                return str(val), f"field:{name}"
        return None

    def _tier2(self, record: LogRecord) -> tuple[str, str] | None:
        msg = record.message or ""
        m = _UUID_RE.search(msg)
        if m:
            return m.group(0), "regex"
        m = _KV_ID_RE.search(msg)
        if m:
            return m.group(1), "regex"
        m = _HEX_RE.search(msg)
        if m:
            return m.group(0), "regex"
        return None

    def resolve(self, records: list[LogRecord]) -> None:
        # Tier 1 and 2 in a first pass; leftovers go to synthesis.
        unresolved: list[LogRecord] = []
        for r in records:
            t1 = self._tier1(r)
            if t1:
                r.flow_id, r.flow_origin = t1
                continue
            t2 = self._tier2(r)
            if t2:
                r.flow_id, r.flow_origin = t2
                continue
            unresolved.append(r)

        # Tier 3: group by (source, thread/pid) and split on time gap.
        groups: dict[tuple[str | None, str | None], list[LogRecord]] = {}
        for r in unresolved:
            key = (r.source, _thread_of(r))
            groups.setdefault(key, []).append(r)

        counter = 0
        for _key, recs in groups.items():
            recs.sort(key=lambda x: (_sortable(x.ts), x.seq))
            current_id: str | None = None
            last_ts: datetime | None = None
            for r in recs:
                gap_exceeded = (
                    current_id is None
                    or (r.ts is not None and last_ts is not None
                        and (r.ts - last_ts).total_seconds() > self.time_gap_seconds)
                )
                if gap_exceeded:
                    counter += 1
                    current_id = f"flow-{counter:04d}"
                r.flow_id = current_id  # type: ignore[assignment]
                r.flow_origin = "synthesized"
                if r.ts is not None:
                    last_ts = r.ts
