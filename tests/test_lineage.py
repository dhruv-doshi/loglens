from loglens.lineage import trace
from loglens.models import LogRecord


def _rec(seq, msg, fields=None):
    return LogRecord(message=msg, seq=seq, raw=msg, fields=fields or {})


def test_trace_returns_matching_subset_in_order():
    records = [
        _rec(0, "request received", fields={"order_id": "ORD-42"}),
        _rec(1, "unrelated event"),
        _rec(2, "processing order ORD-42"),
        _rec(3, "another unrelated event"),
        _rec(4, "shipped", fields={"order_id": "ORD-99"}),
        _rec(5, "order ORD-42 completed"),
    ]
    result = trace(records, "ORD-42")
    assert [r.seq for r in result] == [0, 2, 5]


def test_trace_matches_field_values():
    records = [
        _rec(0, "login", fields={"user_id": "u-7"}),
        _rec(1, "logout", fields={"user_id": "u-8"}),
    ]
    result = trace(records, "u-7")
    assert [r.seq for r in result] == [0]


def test_trace_case_insensitive():
    records = [_rec(0, "User Alice signed in")]
    assert len(trace(records, "alice")) == 1


def test_trace_no_match_empty():
    records = [_rec(0, "nothing here")]
    assert trace(records, "missing") == []
