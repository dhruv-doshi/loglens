import json

import pytest

from loglens.tools import (
    TOOL_SCHEMAS,
    check_expectations,
    find_gaps,
    parse_logs,
    query_logs,
)

_LOG = (
    '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "request received", "trace_id": "A"}\n'
    '{"ts": "2026-01-01T12:00:01Z", "level": "INFO", "msg": "still working", "trace_id": "A"}'
)


def test_parse_logs_json_serializable():
    out = parse_logs(_LOG)
    json.dumps(out)  # must not raise
    assert out["flows"]
    assert out["flows"][0]["flow_id"] == "A"


def test_find_gaps_json_serializable():
    out = find_gaps(_LOG)
    json.dumps(out)
    assert any(a["kind"] == "dangling_start" for a in out["annotations"])


def test_check_expectations_json_serializable(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text("- after: request received\n  expect_one_of: [response sent]\n")
    out = check_expectations(_LOG, str(rules))
    json.dumps(out)
    assert out["annotations"]
    assert out["annotations"][0]["kind"] == "expectation_violation"


def test_query_logs_json_serializable():
    pytest.importorskip("sentence_transformers")
    out = query_logs(_LOG, "working", top_k=2)
    json.dumps(out)
    assert "results" in out
    assert all("score" in r and "record" in r for r in out["results"])


def test_schemas_are_valid_json_schema():
    # One schema per public function, each a JSON-Schema object.
    assert set(TOOL_SCHEMAS) == {
        "parse_logs",
        "query_logs",
        "find_gaps",
        "check_expectations",
    }
    for name, schema in TOOL_SCHEMAS.items():
        json.dumps(schema)  # serializable
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert isinstance(schema["required"], list)
        for req in schema["required"]:
            assert req in schema["properties"]
