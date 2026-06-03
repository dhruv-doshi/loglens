from loglens.gaps import detect_gaps
from loglens.models import Flow, LogRecord


def _rec(seq, msg, level=None, fields=None):
    return LogRecord(
        message=msg,
        seq=seq,
        raw=msg,
        level=level,
        fields=fields or {},
    )


def _flow(records):
    return Flow(flow_id="f1", origin="synthesized", records=records)


def test_dangling_start_fires():
    flow = _flow([
        _rec(0, "request received", level="INFO"),
        _rec(1, "validating payload", level="INFO"),
    ])
    anns = detect_gaps(flow)
    assert len(anns) == 1
    assert anns[0].kind == "dangling_start"
    assert anns[0].record_seq == 0


def test_downgraded_error_fires():
    flow = _flow([
        _rec(0, "request received", level="INFO"),
        _rec(1, "caught Exception: boom", level="INFO"),
        _rec(2, "response sent", level="INFO"),
    ])
    anns = detect_gaps(flow)
    kinds = [a.kind for a in anns]
    assert "downgraded_error" in kinds
    downgrade = next(a for a in anns if a.kind == "downgraded_error")
    assert downgrade.record_seq == 1


def test_unresolved_retry_fires():
    flow = _flow([
        _rec(0, "calling payment gateway", level="INFO"),
        _rec(1, "retrying payment gateway", level="WARN"),
    ])
    anns = detect_gaps(flow)
    assert len(anns) == 1
    assert anns[0].kind == "unresolved_retry"
    assert anns[0].record_seq == 1


def test_clean_flow_silent():
    flow = _flow([
        _rec(0, "request received", level="INFO"),
        _rec(1, "auth token validated", level="INFO"),
        _rec(2, "charge succeeded", level="INFO"),
        _rec(3, "response sent", level="INFO"),
    ])
    assert detect_gaps(flow) == []


def test_resolved_retry_silent():
    flow = _flow([
        _rec(0, "retrying payment gateway", level="WARN"),
        _rec(1, "payment succeeded", level="INFO"),
    ])
    assert detect_gaps(flow) == []


def test_error_level_exception_not_downgraded():
    flow = _flow([
        _rec(0, "Traceback (most recent call last): Exception: boom", level="ERROR"),
    ])
    assert [a for a in detect_gaps(flow) if a.kind == "downgraded_error"] == []
