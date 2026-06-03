from loglens.expectations import Rule, check, load_rules
from loglens.models import Flow, LogRecord


def _rec(seq, msg):
    return LogRecord(message=msg, seq=seq, raw=msg)


def _flow(records):
    return Flow(flow_id="f1", origin="synthesized", records=records)


def test_satisfied_rule_is_silent():
    flow = _flow([
        _rec(0, "charge initiated"),
        _rec(1, "charge confirmed"),
    ])
    rules = [Rule(after="charge initiated", expect_one_of=["confirmed", "refunded"])]
    assert check(flow, rules) == []


def test_violated_rule_flags():
    flow = _flow([
        _rec(0, "charge initiated"),
        _rec(1, "response sent"),
    ])
    rules = [Rule(after="charge initiated", expect_one_of=["confirmed", "refunded"])]
    anns = check(flow, rules)
    assert len(anns) == 1
    assert anns[0].kind == "expectation_violation"
    assert anns[0].record_seq == 0
    assert "confirmed" in anns[0].detail


def test_match_uses_message_not_just_masked_template():
    # Drain3 may collapse "charge accepted" into the template "charge <*>";
    # the literal expected token must still be found via the raw message.
    flow = _flow([
        LogRecord(message="charge initiated", seq=0, raw="charge initiated", template="charge initiated"),
        LogRecord(message="charge accepted", seq=1, raw="charge accepted", template="charge <*>"),
    ])
    rules = [Rule(after="charge initiated", expect_one_of=["charge accepted"])]
    assert check(flow, rules) == []


def test_load_rules_roundtrip(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(
        "- after: charge initiated\n"
        "  expect_one_of: [confirmed, refunded]\n"
        "  within_trace: true\n"
    )
    rules = load_rules(p)
    assert len(rules) == 1
    assert rules[0].after == "charge initiated"
    assert rules[0].expect_one_of == ["confirmed", "refunded"]
    assert rules[0].within_trace is True
