from datetime import datetime, timedelta

from loglens.models import Flow, LogRecord
from loglens.render import render_flows


def _rec(seq, ts=None, level=None, source=None, template_id=None, template=None, message="m"):
    return LogRecord(
        message=message,
        seq=seq,
        raw=message,
        ts=ts,
        level=level,
        source=source,
        template_id=template_id,
        template=template,
    )


def test_header_format():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    f = Flow(
        flow_id="abc",
        origin="field:trace_id",
        records=[_rec(0, ts=t0), _rec(1, ts=t0 + timedelta(seconds=2))],
    )
    out = render_flows([f])
    header = out.splitlines()[0]
    assert header.startswith("abc  (origin: field:trace_id)  ·  2 events  ·  ")
    assert "0:00:02" in header


def test_collapse_consecutive_templates():
    f = Flow(
        flow_id="abc",
        origin="regex",
        records=[
            _rec(0, template_id="T0001", template="user <NUM> connected"),
            _rec(1, template_id="T0001", template="user <NUM> connected"),
            _rec(2, template_id="T0001", template="user <NUM> connected"),
            _rec(3, template_id="T0002", template="db query <NUM>"),
        ],
    )
    out = render_flows([f])
    lines = out.splitlines()
    # header + 2 collapsed record lines
    assert len(lines) == 3
    assert lines[1].endswith("×3")
    assert "user <NUM> connected" in lines[1]
    assert lines[2].endswith("db query <NUM>")


def test_handles_missing_fields():
    f = Flow(
        flow_id="x",
        origin="synthesized",
        records=[_rec(0, message="raw msg")],
    )
    out = render_flows([f])
    assert "x" in out
    assert "raw msg" in out
    assert "-" in out  # missing ts/level/source rendered as "-"


def test_no_duration_when_no_timestamps():
    f = Flow(flow_id="x", origin="synthesized", records=[_rec(0)])
    out = render_flows([f])
    header = out.splitlines()[0]
    assert header.endswith("·  -")
