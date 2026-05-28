import logging

from loglens.lens import LogLens, LogLensHandler


def test_end_to_end_ingest_groups_flows():
    lines = [
        '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "start", "trace_id": "A"}',
        '{"ts": "2026-01-01T12:00:01Z", "level": "INFO", "msg": "step", "trace_id": "A"}',
        '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "begin", "trace_id": "B"}',
        '{"ts": "2026-01-01T12:00:02Z", "level": "ERROR", "msg": "boom", "trace_id": "B"}',
    ]
    lens = LogLens()
    lens.ingest(lines)
    flows = lens.flows()
    by_id = {f.flow_id: f for f in flows}
    assert set(by_id) == {"A", "B"}
    assert by_id["A"].event_count == 2
    assert by_id["B"].event_count == 2
    assert all(f.origin == "field:trace_id" for f in flows)


def test_show_returns_rendered_output():
    lens = LogLens()
    lens.ingest(['{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "hi", "trace_id": "A"}'])
    out = lens.show()
    assert "A" in out
    assert "field:trace_id" in out


def test_ingest_from_file(tmp_path):
    p = tmp_path / "sample.log"
    p.write_text(
        '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "x", "trace_id": "F"}\n'
        '{"ts": "2026-01-01T12:00:01Z", "level": "INFO", "msg": "y", "trace_id": "F"}\n'
    )
    lens = LogLens()
    lens.ingest(p)
    flows = lens.flows()
    assert len(flows) == 1
    assert flows[0].flow_id == "F"


def test_handler_captures_emitted_logs():
    lens = LogLens()
    handler = LogLensHandler(lens)
    logger = logging.getLogger("loglens.test")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("hello from test")
    logger.error("something failed with code %d", 42)

    assert len(lens._records) == 2
    assert lens._records[0].message == "hello from test"
    assert lens._records[0].level == "INFO"
    assert lens._records[0].source == "loglens.test"
    assert lens._records[0].ts is not None
    assert lens._records[1].message == "something failed with code 42"
    assert lens._records[1].level == "ERROR"
