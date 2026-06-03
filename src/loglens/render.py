from __future__ import annotations

import json
import re

from .colors import BOLD, CYAN, DIM, MAGENTA, level_color, paint
from .models import Flow, LogRecord

_PLACEHOLDER_RE = re.compile(r"<[A-Z*]+>|<\*>")


def _fmt_ts(r: LogRecord) -> str:
    return r.ts.isoformat() if r.ts is not None else "-"


def _fmt_text(r: LogRecord, color: bool, use_template: bool) -> str:
    text = (r.template or r.message) if use_template else (r.message or r.raw)
    if not color:
        return text
    return _PLACEHOLDER_RE.sub(lambda m: paint(m.group(0), DIM, True), text)


def _fmt_record(r: LogRecord, color: bool, use_template: bool = True) -> str:
    ts = paint(_fmt_ts(r), DIM, color)
    level_raw = r.level or "-"
    level = paint(level_raw, level_color(r.level), color) if r.level else level_raw
    source_raw = r.source or "-"
    source = paint(source_raw, MAGENTA, color) if r.source else source_raw
    return f"  {ts}  {level}  {source}  {_fmt_text(r, color, use_template)}"


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


def format_query_result(record: LogRecord, score: float, *, color: bool = False) -> str:
    score_str = paint(f"{score:.3f}", DIM, color)
    return f"{score_str}{_fmt_record(record, color)}"


def render_annotations(annotations, *, color: bool = False) -> str:
    """Render gap/expectation Annotations grouped by flow_id."""
    if not annotations:
        return "No anomalies detected."
    by_flow: dict[str, list] = {}
    for a in annotations:
        by_flow.setdefault(a.flow_id, []).append(a)
    out: list[str] = []
    for fid, anns in by_flow.items():
        out.append(paint(fid, CYAN + BOLD, color))
        for a in anns:
            kind = paint(a.kind, level_color("WARN"), color)
            seq = paint(f"seq={a.record_seq}", DIM, color)
            out.append(f"  [{kind}]  {seq}  {a.detail}")
        out.append("")
    return "\n".join(out).rstrip("\n")


def render_lineage(records: list[LogRecord], *, color: bool = False) -> str:
    """Render matching records with their flow_id shown, so an entity can be
    followed across flows."""
    if not records:
        return "No matching records."
    out: list[str] = []
    for r in records:
        fid = paint(r.flow_id or "-", CYAN, color)
        out.append(f"{fid}{_fmt_record(r, color, use_template=False)}")
    return "\n".join(out)


def record_to_dict(r: LogRecord) -> dict:
    """Canonical JSON-serializable view of a LogRecord."""
    return {
        "ts": r.ts.isoformat() if r.ts is not None else None,
        "level": r.level,
        "source": r.source,
        "message": r.message,
        "template": r.template,
        "template_id": r.template_id,
        "flow_id": r.flow_id,
        "flow_origin": r.flow_origin,
        "seq": r.seq,
        "fields": r.fields,
    }


def flow_to_dict(flow: Flow) -> dict:
    """Canonical JSON-serializable view of a Flow."""
    return {
        "flow_id": flow.flow_id,
        "origin": flow.origin,
        "event_count": flow.event_count,
        "duration_seconds": (
            flow.duration.total_seconds() if flow.duration is not None else None
        ),
        "records": [record_to_dict(r) for r in flow.records],
    }


def render_flows_json(flows: list[Flow]) -> str:
    """Render flows as a JSON string for machine consumers."""
    return json.dumps({"flows": [flow_to_dict(f) for f in flows]}, indent=2)


def _mermaid_label(r: LogRecord) -> str:
    text = (r.template or r.message or "").replace("\n", " ").replace('"', "'")
    label = f"{r.level or ''} {text}".strip()
    return label[:80] if label else "(empty)"


def render_flows_mermaid(flows: list[Flow]) -> str:
    """Render the flow tree as a Mermaid flowchart string."""
    lines = ["flowchart TD"]
    for fi, flow in enumerate(flows):
        safe_fid = re.sub(r"\W", "_", flow.flow_id) or f"flow{fi}"
        lines.append(f'  subgraph {safe_fid}["{flow.flow_id} ({flow.origin})"]')
        prev = None
        for ri, r in enumerate(flow.records):
            nid = f"n{fi}_{ri}"
            lines.append(f'    {nid}["{_mermaid_label(r)}"]')
            if prev is not None:
                lines.append(f"    {prev} --> {nid}")
            prev = nid
        lines.append("  end")
    return "\n".join(lines)


def render_flows(
    flows: list[Flow], *, color: bool = False, use_template: bool = True
) -> str:
    out: list[str] = []
    for flow in flows:
        out.append(_fmt_header(flow, color))
        i = 0
        recs = flow.records
        while i < len(recs):
            r = recs[i]
            count = 1
            if use_template and r.template_id is not None:
                j = i + 1
                while j < len(recs) and recs[j].template_id == r.template_id:
                    count += 1
                    j += 1
            else:
                j = i + 1
            line = _fmt_record(r, color, use_template)
            if count > 1:
                line += paint(f"  ×{count}", DIM, color)
            out.append(line)
            i = j
        out.append("")
    return "\n".join(out).rstrip("\n")
