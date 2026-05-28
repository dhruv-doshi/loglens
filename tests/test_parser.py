from loglens.models import LogRecord
from loglens.parser import TemplateParser


def _rec(msg, seq=0):
    return LogRecord(message=msg, seq=seq, raw=msg)


def test_variants_collapse_to_one_template():
    p = TemplateParser()
    rs = [
        p.assign(_rec("user 42 connected from 10.0.0.1")),
        p.assign(_rec("user 7 connected from 192.168.1.5")),
        p.assign(_rec("user 1024 connected from 172.16.0.9")),
    ]
    ids = {r.template_id for r in rs}
    assert len(ids) == 1
    assert rs[0].template is not None


def test_distinct_messages_get_distinct_templates():
    p = TemplateParser()
    a = p.assign(_rec("user 42 connected from 10.0.0.1"))
    b = p.assign(_rec("database query failed with timeout"))
    assert a.template_id != b.template_id


def test_template_id_format():
    p = TemplateParser()
    r = p.assign(_rec("hello world"))
    assert r.template_id is not None
    assert r.template_id.startswith("T") and len(r.template_id) == 5
