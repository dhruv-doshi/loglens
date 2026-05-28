from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class LogRecord:
    message: str
    seq: int
    raw: str
    ts: datetime | None = None
    level: str | None = None
    source: str | None = None
    template_id: str | None = None
    template: str | None = None
    flow_id: str = ""
    flow_origin: str = ""
    fields: dict = field(default_factory=dict)


@dataclass
class Flow:
    flow_id: str
    origin: str
    records: list[LogRecord]

    @property
    def start_ts(self) -> datetime | None:
        for r in self.records:
            if r.ts is not None:
                return r.ts
        return None

    @property
    def end_ts(self) -> datetime | None:
        for r in reversed(self.records):
            if r.ts is not None:
                return r.ts
        return None

    @property
    def duration(self) -> timedelta | None:
        s, e = self.start_ts, self.end_ts
        if s is None or e is None:
            return None
        return e - s

    @property
    def event_count(self) -> int:
        return len(self.records)


def build_flows(records: list[LogRecord]) -> list[Flow]:
    groups: dict[str, list[LogRecord]] = {}
    origins: dict[str, str] = {}
    for r in records:
        groups.setdefault(r.flow_id, []).append(r)
        origins.setdefault(r.flow_id, r.flow_origin)

    flows: list[Flow] = []
    for fid, recs in groups.items():
        recs.sort(key=lambda r: (r.ts or datetime.min, r.seq))
        flows.append(Flow(flow_id=fid, origin=origins[fid], records=recs))

    flows.sort(key=lambda f: f.start_ts or datetime.min)
    return flows
