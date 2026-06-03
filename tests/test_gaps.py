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


def test_confirmed_terminal_suppresses_dangling_start():
    # A successful checkout ending in "order confirmed" must not be flagged.
    flow = _flow([
        _rec(0, "request received", level="INFO"),
        _rec(1, "charge accepted", level="INFO"),
        _rec(2, "order confirmed", level="INFO"),
    ])
    assert [a for a in detect_gaps(flow) if a.kind == "dangling_start"] == []


def test_swallowed_camelcase_exception_downgraded():
    # No literal "exception"/"traceback", but a CamelCase *Timeout caught at INFO.
    flow = _flow([
        _rec(0, "caught PaymentGatewayTimeout: upstream did not respond; continuing", level="INFO"),
    ])
    anns = detect_gaps(flow)
    assert any(a.kind == "downgraded_error" for a in anns)


def test_plain_timeout_message_at_warn_not_downgraded():
    # A lowercase "timed out" at WARN is the condition being retried, not a
    # swallowed exception — must stay quiet to avoid noise.
    flow = _flow([
        _rec(0, "payment gateway call timed out after 500ms", level="WARN"),
    ])
    assert [a for a in detect_gaps(flow) if a.kind == "downgraded_error"] == []


def test_retry_not_resolved_by_vague_confirmed():
    # "order confirmed" is a flow-level terminal, not proof the retried payment
    # succeeded — the unresolved retry must still surface.
    flow = _flow([
        _rec(0, "retrying payment gateway", level="INFO"),
        _rec(1, "caught PaymentGatewayTimeout: continuing without confirmation", level="INFO"),
        _rec(2, "order confirmed", level="INFO"),
    ])
    anns = detect_gaps(flow)
    assert any(a.kind == "unresolved_retry" for a in anns)


def test_retry_resolved_by_success():
    flow = _flow([
        _rec(0, "retrying payment gateway", level="WARN"),
        _rec(1, "payment recovered", level="INFO"),
    ])
    assert [a for a in detect_gaps(flow) if a.kind == "unresolved_retry"] == []
