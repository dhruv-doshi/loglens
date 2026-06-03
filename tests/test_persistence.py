from loglens.models import LogRecord
from loglens.parser import TemplateParser


def _rec(msg):
    return LogRecord(message=msg, seq=0, raw=msg)


def test_template_ids_persist_across_parsers(tmp_path):
    state = tmp_path / "drain.state"

    first = TemplateParser(state_path=state)
    r1 = first.assign(_rec("user 42 logged in from 10.0.0.1"))
    first_id = r1.template_id
    assert first_id is not None
    assert state.exists()

    # A brand-new parser pointing at the same state file must reuse the id.
    second = TemplateParser(state_path=state)
    r2 = second.assign(_rec("user 99 logged in from 10.0.0.2"))
    assert r2.template_id == first_id


def test_in_memory_default_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    parser = TemplateParser()
    parser.assign(_rec("hello world"))
    # No state file created in the default (in-memory) mode.
    assert list(tmp_path.iterdir()) == []
