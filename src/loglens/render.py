from __future__ import annotations

from .models import Flow, LogRecord


def _fmt_ts(r: LogRecord) -> str:
    return r.ts.isoformat() if r.ts is not None else "-"


def _fmt_text(r: LogRecord) -> str:
    return r.template or r.message


def _fmt_record(r: LogRecord) -> str:
    return f"  {_fmt_ts(r)}  {r.level or '-'}  {r.source or '-'}  {_fmt_text(r)}"


def _fmt_duration(flow: Flow) -> str:
    d = flow.duration
    return str(d) if d is not None else "-"


def _fmt_header(flow: Flow) -> str:
    return (
        f"{flow.flow_id}  (origin: {flow.origin})  ·  "
        f"{flow.event_count} events  ·  {_fmt_duration(flow)}"
    )


def render_flows(flows: list[Flow]) -> str:
    out: list[str] = []
    for flow in flows:
        out.append(_fmt_header(flow))
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
            line = _fmt_record(r)
            if count > 1:
                line += f"  ×{count}"
            out.append(line)
            i = j
        out.append("")
    return "\n".join(out).rstrip("\n")
