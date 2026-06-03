"""Agent-facing tool surface: thin wrappers over LogLens with JSON-serializable
arguments and return values, plus a JSON Schema per function. No new core logic."""

from __future__ import annotations

from .lens import LogLens
from .render import flow_to_dict, record_to_dict


def _lens(text: str) -> LogLens:
    lens = LogLens()
    lens.ingest(text.splitlines())
    return lens


def _annotation_dict(a) -> dict:
    return {
        "flow_id": a.flow_id,
        "record_seq": a.record_seq,
        "kind": a.kind,
        "detail": a.detail,
    }


def parse_logs(text: str) -> dict:
    """Parse raw log text into reconstructed, correlated flows."""
    lens = _lens(text)
    return {"flows": [flow_to_dict(f) for f in lens.flows()]}


def query_logs(text: str, query: str, top_k: int = 10) -> dict:
    """Rank log lines by semantic relevance to a query. Requires the 'ai' extra."""
    lens = _lens(text)
    results = lens.query(query, top_k=top_k)
    return {
        "results": [
            {"score": float(score), "record": record_to_dict(rec)}
            for rec, score in results
        ]
    }


def find_gaps(text: str) -> dict:
    """Detect structural anomalies: dangling starts, downgraded errors, unresolved retries."""
    lens = _lens(text)
    annotations = [a for anns in lens.gaps().values() for a in anns]
    return {"annotations": [_annotation_dict(a) for a in annotations]}


def check_expectations(text: str, rules_path: str) -> dict:
    """Check declared YAML expectation rules against the reconstructed flows."""
    lens = _lens(text)
    return {
        "annotations": [_annotation_dict(a) for a in lens.check_expectations(rules_path)]
    }


_TEXT_PROP = {"type": "string", "description": "Raw log text, one record per line."}

TOOL_SCHEMAS: dict[str, dict] = {
    "parse_logs": {
        "type": "object",
        "properties": {"text": _TEXT_PROP},
        "required": ["text"],
    },
    "query_logs": {
        "type": "object",
        "properties": {
            "text": _TEXT_PROP,
            "query": {"type": "string", "description": "Natural-language query."},
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results.",
                "default": 10,
            },
        },
        "required": ["text", "query"],
    },
    "find_gaps": {
        "type": "object",
        "properties": {"text": _TEXT_PROP},
        "required": ["text"],
    },
    "check_expectations": {
        "type": "object",
        "properties": {
            "text": _TEXT_PROP,
            "rules_path": {
                "type": "string",
                "description": "Path to a YAML expectation-rules file.",
            },
        },
        "required": ["text", "rules_path"],
    },
}
