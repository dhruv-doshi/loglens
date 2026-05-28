from datetime import datetime, timedelta, timezone

from loglens.models import Flow, LogRecord, build_flows


def _rec(seq, flow_id, ts=None, origin="field:trace_id", message="m"):
    return LogRecord(
        message=message,
        seq=seq,
        raw=message,
        ts=ts,
        flow_id=flow_id,
        flow_origin=origin,
    )


def test_build_flows_groups_by_flow_id():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    records = [
        _rec(0, "A", ts=t0),
        _rec(1, "B", ts=t0 + timedelta(seconds=1)),
        _rec(2, "A", ts=t0 + timedelta(seconds=2)),
    ]
    flows = build_flows(records)
    by_id = {f.flow_id: f for f in flows}
    assert set(by_id) == {"A", "B"}
    assert [r.seq for r in by_id["A"].records] == [0, 2]
    assert [r.seq for r in by_id["B"].records] == [1]


def test_build_flows_orders_by_seq_when_ts_ties():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    records = [
        _rec(2, "A", ts=t0),
        _rec(0, "A", ts=t0),
        _rec(1, "A", ts=t0),
    ]
    flows = build_flows(records)
    assert [r.seq for r in flows[0].records] == [0, 1, 2]


def test_flows_sorted_by_start_ts():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    records = [
        _rec(0, "late", ts=t0 + timedelta(seconds=10)),
        _rec(1, "early", ts=t0),
    ]
    flows = build_flows(records)
    assert [f.flow_id for f in flows] == ["early", "late"]


def test_flow_properties():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    recs = [
        _rec(0, "A", ts=t0),
        _rec(1, "A", ts=None),
        _rec(2, "A", ts=t0 + timedelta(seconds=5)),
    ]
    flow = Flow(flow_id="A", origin="field:trace_id", records=recs)
    assert flow.start_ts == t0
    assert flow.end_ts == t0 + timedelta(seconds=5)
    assert flow.duration == timedelta(seconds=5)
    assert flow.event_count == 3


def test_build_flows_mixes_naive_and_aware_timestamps():
    # Regression: real logs interleave tz-aware (ISO with Z) and naive
    # (syslog, missing ts → datetime.min) timestamps. Sorting must not crash.
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1, 12, 0, 1)
    records = [
        _rec(0, "A", ts=aware),
        _rec(1, "A", ts=naive),
        _rec(2, "B", ts=None),
        _rec(3, "B", ts=aware),
    ]
    flows = build_flows(records)
    assert {f.flow_id for f in flows} == {"A", "B"}


def test_flow_properties_no_timestamps():
    recs = [_rec(0, "A"), _rec(1, "A")]
    flow = Flow(flow_id="A", origin="synthesized", records=recs)
    assert flow.start_ts is None
    assert flow.end_ts is None
    assert flow.duration is None
    assert flow.event_count == 2
