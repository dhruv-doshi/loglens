import gzip
import json

from loglens.lens import LogLens
from loglens.render import render_flows_json, render_flows_mermaid

_NDJSON = (
    '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "a", "trace_id": "A"}\n'
    '{"ts": "2026-01-01T12:00:01Z", "level": "INFO", "msg": "b", "trace_id": "A"}\n'
)


def test_gz_file_ingests(tmp_path):
    p = tmp_path / "logs.ndjson.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        fh.write(_NDJSON)
    lens = LogLens()
    lens.ingest(p)
    flows = lens.flows()
    assert len(flows) == 1
    assert flows[0].flow_id == "A"
    assert flows[0].event_count == 2


def test_ndjson_plain_file_ingests(tmp_path):
    p = tmp_path / "logs.ndjson"
    p.write_text(_NDJSON)
    lens = LogLens()
    lens.ingest(p)
    assert lens.flows()[0].flow_id == "A"


def test_render_flows_json_round_trips():
    lens = LogLens()
    lens.ingest(_NDJSON.splitlines())
    out = render_flows_json(lens.flows())
    parsed = json.loads(out)
    assert parsed["flows"][0]["flow_id"] == "A"
    assert len(parsed["flows"][0]["records"]) == 2


def test_render_flows_mermaid_emits_flowchart():
    lens = LogLens()
    lens.ingest(_NDJSON.splitlines())
    out = render_flows_mermaid(lens.flows())
    assert out.startswith("flowchart TD")
    assert "-->" in out
    assert "subgraph" in out
