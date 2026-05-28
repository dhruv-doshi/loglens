from datetime import datetime, timedelta

from loglens.correlate import Correlator
from loglens.models import LogRecord


def _rec(seq, msg="m", ts=None, fields=None, source=None):
    return LogRecord(
        message=msg,
        seq=seq,
        raw=msg,
        ts=ts,
        source=source,
        fields=fields or {},
    )


def test_tier1_field():
    records = [
        _rec(0, fields={"trace_id": "abc"}),
        _rec(1, fields={"trace_id": "abc"}),
        _rec(2, fields={"trace_id": "xyz"}),
    ]
    Correlator().resolve(records)
    assert records[0].flow_id == "abc"
    assert records[0].flow_origin == "field:trace_id"
    assert records[1].flow_id == "abc"
    assert records[2].flow_id == "xyz"


def test_tier2_regex_uuid_in_message():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    records = [
        _rec(0, msg=f"start request {uuid}"),
        _rec(1, msg=f"finish request {uuid}"),
        _rec(2, msg="unrelated 11112222-3333-4444-5555-666677778888"),
    ]
    Correlator().resolve(records)
    assert records[0].flow_id == uuid
    assert records[0].flow_origin == "regex"
    assert records[1].flow_id == uuid
    assert records[2].flow_id != uuid
    assert records[2].flow_origin == "regex"


def test_tier3_synthesized_splits_on_time_gap():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    records = [
        _rec(0, ts=t0, source="svc"),
        _rec(1, ts=t0 + timedelta(seconds=1), source="svc"),
        _rec(2, ts=t0 + timedelta(seconds=20), source="svc"),
        _rec(3, ts=t0 + timedelta(seconds=21), source="svc"),
    ]
    Correlator(time_gap_seconds=5.0).resolve(records)
    assert records[0].flow_id == records[1].flow_id
    assert records[2].flow_id == records[3].flow_id
    assert records[0].flow_id != records[2].flow_id
    assert all(r.flow_origin == "synthesized" for r in records)
    assert records[0].flow_id.startswith("flow-")


def test_tiers_combine():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    records = [
        _rec(0, fields={"trace_id": "T1"}, ts=t0),
        _rec(1, msg="op id=req-abcd1234", ts=t0 + timedelta(seconds=1)),
        _rec(2, ts=t0 + timedelta(seconds=2), source="svc"),
    ]
    Correlator().resolve(records)
    assert records[0].flow_origin == "field:trace_id"
    assert records[1].flow_origin == "regex"
    assert records[2].flow_origin == "synthesized"
