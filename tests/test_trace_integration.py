from loglens.lens import LogLens

_THIS_FILE = __file__


def _inner(x):
    return x * 2


def _outer():
    return _inner(21)


def test_facade_trace_renders_alongside_logs():
    lens = LogLens()
    lens.ingest(['{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "log line", "trace_id": "A"}'])

    with lens.trace(include=[_THIS_FILE]):
        _outer()

    out = lens.show()
    # The log flow and the traced flow both appear.
    assert "field:trace_id" in out
    assert "trace-0001" in out
    assert "_outer" in out
    assert "_inner" in out


def test_trace_flows_visible_to_gaps():
    lens = LogLens()
    with lens.trace(include=[_THIS_FILE]):
        _outer()
    # gaps() must run over traced flows without raising.
    assert "trace-0001" in lens.gaps()
