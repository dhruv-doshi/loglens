import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

from loglens.analyzer import EmbeddingQuery
from loglens.models import LogRecord


def _rec(seq, msg, template_id=None):
    return LogRecord(
        message=msg,
        seq=seq,
        raw=msg,
        template_id=template_id,
        template=msg,
    )


def test_query_ranks_relevant_line_in_top_k():
    records = [
        _rec(0, "user logged in successfully", "T0001"),
        _rec(1, "cache miss for key foo", "T0002"),
        _rec(2, "connection refused by upstream server", "T0003"),
        _rec(3, "background job scheduled", "T0004"),
        _rec(4, "request completed in 12ms", "T0005"),
    ]
    eq = EmbeddingQuery()
    results = eq.query(records, "network connection failure", top_k=3)
    assert len(results) <= 3
    top_msgs = [r.message for r, _ in results]
    assert "connection refused by upstream server" in top_msgs
    # Scores must be descending.
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_query_dedups_by_template_id():
    records = [
        _rec(0, "connection refused 1", "T0001"),
        _rec(1, "connection refused 2", "T0001"),
        _rec(2, "cache miss", "T0002"),
    ]
    eq = EmbeddingQuery()
    results = eq.query(records, "connection", top_k=10)
    # Two unique templates → at most 2 results.
    assert len(results) == 2


def test_query_empty_records():
    eq = EmbeddingQuery()
    assert eq.query([], "anything", top_k=5) == []
