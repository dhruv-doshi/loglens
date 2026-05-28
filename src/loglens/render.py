from __future__ import annotations

import re

from .colors import BOLD, CYAN, DIM, MAGENTA, level_color, paint
from .models import Flow, LogRecord

_PLACEHOLDER_RE = re.compile(r"<[A-Z*]+>|<\*>")


def _fmt_ts(r: LogRecord) -> str:
    return r.ts.isoformat() if r.ts is not None else "-"


def _fmt_text(r: LogRecord, color: bool) -> str:
    text = r.template or r.message
    if not color:
        return text
    return _PLACEHOLDER_RE.sub(lambda m: paint(m.group(0), DIM, True), text)


def _fmt_record(r: LogRecord, color: bool) -> str:
    ts = paint(_fmt_ts(r), DIM, color)
    level_raw = r.level or "-"
    level = paint(level_raw, level_color(r.level), color) if r.level else level_raw
    source_raw = r.source or "-"
    source = paint(source_raw, MAGENTA, color) if r.source else source_raw
    return f"  {ts}  {level}  {source}  {_fmt_text(r, color)}"


def _fmt_duration(flow: Flow) -> str:
    d = flow.duration
    return str(d) if d is not None else "-"


def _fmt_header(flow: Flow, color: bool) -> str:
    flow_id = paint(flow.flow_id, CYAN + BOLD, color)
    origin = paint(f"origin: {flow.origin}", DIM, color)
    return (
        f"{flow_id}  ({origin})  ·  "
        f"{flow.event_count} events  ·  {_fmt_duration(flow)}"
    )


def render_flows(flows: list[Flow], *, color: bool = False) -> str:
    out: list[str] = []
    for flow in flows:
        out.append(_fmt_header(flow, color))
        i = 0
        recs = flow.records
        while i < len(recs):
            r = recs[i]
            count = 1
            if r.template_id is not None:
                j = i + 1
                while j < len(recs) and recs[j].template_id == r.template_id:
                    count += 1
                    j += 1
            else:
                j = i + 1
            line = _fmt_record(r, color)
            if count > 1:
                line += paint(f"  ×{count}", DIM, color)
            out.append(line)
            i = j
        out.append("")
    return "\n".join(out).rstrip("\n")
