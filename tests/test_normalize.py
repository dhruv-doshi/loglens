from datetime import datetime

from loglens.normalize import normalize_line


def test_json_line():
    raw = '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "hello", "user": "x"}'
    r = normalize_line(raw, 0)
    assert r.message == "hello"
    assert r.level == "INFO"
    assert r.ts == datetime.fromisoformat("2026-01-01T12:00:00+00:00")
    assert r.fields == {"user": "x"}
    assert r.raw == raw


def test_logfmt_line():
    raw = 'ts=2026-01-01T12:00:00Z level=ERROR msg="conn refused" host=db1'
    r = normalize_line(raw, 1)
    assert r.message == "conn refused"
    assert r.level == "ERROR"
    assert r.ts == datetime.fromisoformat("2026-01-01T12:00:00+00:00")
    assert r.fields.get("host") == "db1"


def test_iso_level_message():
    raw = "2026-01-01T12:00:00 INFO server started on :8080"
    r = normalize_line(raw, 2)
    assert r.level == "INFO"
    assert r.message == "server started on :8080"
    assert r.ts == datetime(2026, 1, 1, 12, 0, 0)


def test_syslog_line():
    raw = "Jan  1 12:00:00 host1 sshd: accepted password for root"
    r = normalize_line(raw, 3)
    assert r.message == "accepted password for root"
    assert r.source == "host1/sshd"
    assert r.ts is not None
    assert r.ts.month == 1 and r.ts.day == 1


def test_garbage_does_not_raise():
    raw = "@@@ totally not a log line ###"
    r = normalize_line(raw, 4)
    assert r.message == raw
    assert r.raw == raw
    assert r.ts is None


def test_fallback_sniffs_level():
    raw = "something happened ERROR in the middle"
    r = normalize_line(raw, 5)
    assert r.level == "ERROR"
    assert r.message == raw
