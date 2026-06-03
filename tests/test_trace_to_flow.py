from datetime import datetime, timedelta

from loglens.render import render_flows
from loglens.tracer import CallEvent
from loglens.trace_to_flow import to_flows

T0 = datetime(2026, 1, 1, 0, 0, 0)


def _ev(qual, depth, tid, offset, dur=0.1):
    return CallEvent(
        qualname=qual,
        module="app.mod",
        filename="/app/mod.py",
        lineno=10,
        depth=depth,
        thread_id=tid,
        t_enter=T0 + timedelta(seconds=offset),
        t_exit=T0 + timedelta(seconds=offset + dur),
    )


def test_single_root_one_flow():
    events = [
        _ev("root", 0, 1, 0),
        _ev("helper", 1, 1, 0.01),
        _ev("leaf", 2, 1, 0.02),
    ]
    flows = to_flows(events)
    assert len(flows) == 1
    assert flows[0].flow_id == "trace-0001"
    assert flows[0].origin == "trace"
    assert flows[0].event_count == 3


def test_two_roots_two_flows():
    events = [
        _ev("root", 0, 1, 0),
        _ev("helper", 1, 1, 0.01),
        _ev("root", 0, 1, 1.0),
    ]
    flows = to_flows(events)
    assert len(flows) == 2
    assert {f.flow_id for f in flows} == {"trace-0001", "trace-0002"}


def test_separate_threads_separate_flows():
    events = [
        _ev("root", 0, 1, 0),
        _ev("root", 0, 2, 0.01),
    ]
    flows = to_flows(events)
    assert len(flows) == 2


def test_renders_with_existing_renderer():
    events = [_ev("root", 0, 1, 0), _ev("leaf", 1, 1, 0.01)]
    out = render_flows(to_flows(events))
    assert "trace-0001" in out
    assert "root" in out
    assert "leaf" in out


def test_fields_carry_depth_and_duration():
    flows = to_flows([_ev("root", 0, 1, 0, dur=0.5)])
    rec = flows[0].records[0]
    assert rec.fields["depth"] == 0
    assert rec.fields["lineno"] == 10
    assert abs(rec.fields["duration"] - 0.5) < 1e-6
