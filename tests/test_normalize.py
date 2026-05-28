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


def test_bracketed_python_logging():
    raw = "[2026-05-28 10:32:00,123] ERROR django.request: Internal Server Error: /x/"
    r = normalize_line(raw, 0)
    assert r.level == "ERROR"
    assert r.source == "django.request"
    assert r.message == "Internal Server Error: /x/"
    assert r.ts is not None
    assert r.ts.microsecond == 123000


def test_k8s_cri_prefix_strips_and_recurses_into_json():
    raw = (
        '2026-05-28T10:32:00.123456789Z stdout F '
        '{"level":"info","msg":"job picked","job_id":"j-7c1f"}'
    )
    r = normalize_line(raw, 0)
    assert r.message == "job picked"
    assert r.level == "INFO"
    assert r.fields.get("job_id") == "j-7c1f"
    assert r.source == "stdout" or r.source is not None
    assert r.ts is not None
    assert r.raw == raw


def test_apache_combined_format():
    raw = (
        '192.168.1.10 - - [28/May/2026:10:32:00 +0000] '
        '"POST /api/checkout HTTP/1.1" 502 0 '
        '"https://shop.example.com" "Mozilla/5.0"'
    )
    r = normalize_line(raw, 0)
    assert r.message == "POST /api/checkout HTTP/1.1"
    assert r.level == "ERROR"  # 5xx
    assert r.source == "192.168.1.10"
    assert r.fields.get("status") == "502"
    assert r.ts is not None


def test_apache_4xx_maps_to_warn():
    raw = '10.0.0.1 - - [28/May/2026:10:32:00 +0000] "GET /admin HTTP/1.1" 401 0 "-" "curl/8"'
    r = normalize_line(raw, 0)
    assert r.level == "WARN"


def test_is_continuation_detects_indented_lines():
    from loglens.normalize import is_continuation
    assert is_continuation("  File \"/app/x.py\"")
    assert is_continuation("\tindented")
    assert not is_continuation("INFO message")
    assert not is_continuation("")


def test_is_continuation_catches_traceback_bookends():
    from loglens.normalize import is_continuation
    assert is_continuation("Traceback (most recent call last):")
    assert is_continuation("ValueError: bad input")
    assert is_continuation("app.payment.PaymentGatewayError: upstream timeout")
    assert is_continuation("ConnectionResetError: [Errno 54] Connection reset by peer")
    # Not exception-shaped — must not be merged.
    assert not is_continuation("Service started")
    assert not is_continuation("user logged in")
