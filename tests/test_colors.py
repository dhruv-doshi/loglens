from datetime import datetime

from loglens.colors import RESET, level_color, should_color
from loglens.models import Flow, LogRecord
from loglens.render import render_flows


def _rec(seq, **kw):
    return LogRecord(message="m", seq=seq, raw="m", **kw)


def test_level_color_maps_known_levels():
    assert level_color("INFO")
    assert level_color("error") == level_color("ERROR")
    assert level_color(None) == ""
    assert level_color("BANANA") == ""


def test_should_color_respects_no_color_env(monkeypatch):
    class FakeTTY:
        def isatty(self):
            return True

    monkeypatch.setenv("NO_COLOR", "1")
    assert should_color(FakeTTY()) is False
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert should_color(FakeTTY()) is True


def test_should_color_false_for_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    class NotTTY:
        def isatty(self):
            return False

    assert should_color(NotTTY()) is False


def test_render_color_off_has_no_ansi():
    f = Flow(
        flow_id="A",
        origin="field:trace_id",
        records=[_rec(0, ts=datetime(2026, 1, 1), level="ERROR", source="svc")],
    )
    out = render_flows([f], color=False)
    assert "\x1b[" not in out


def test_render_color_on_emits_ansi_and_resets():
    f = Flow(
        flow_id="A",
        origin="field:trace_id",
        records=[_rec(0, ts=datetime(2026, 1, 1), level="ERROR", source="svc")],
    )
    out = render_flows([f], color=True)
    assert "\x1b[" in out
    assert RESET in out
    # Header flow_id and level should be painted.
    assert "A" in out and "ERROR" in out
