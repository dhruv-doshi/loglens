from loglens.cli import main


def test_cli_prints_flows(tmp_path, capsys):
    p = tmp_path / "sample.log"
    p.write_text(
        '{"ts": "2026-01-01T12:00:00Z", "level": "INFO", "msg": "go", "trace_id": "Z"}\n'
        '{"ts": "2026-01-01T12:00:01Z", "level": "INFO", "msg": "done", "trace_id": "Z"}\n'
    )
    rc = main([str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Z" in out
    assert "field:trace_id" in out


def test_cli_query_without_ai_extra_exits_clean(tmp_path, capsys, monkeypatch):
    p = tmp_path / "sample.log"
    p.write_text('{"ts": "2026-01-01T12:00:00Z", "msg": "x", "trace_id": "A"}\n')

    import loglens.analyzer as analyzer_mod

    def raise_missing(*a, **kw):
        raise RuntimeError(
            "Semantic query requires the 'ai' extra. "
            "Install it with: pip install loglens[ai]"
        )

    monkeypatch.setattr(analyzer_mod, "EmbeddingQuery", raise_missing)

    rc = main([str(p), "--query", "boom"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "loglens[ai]" in err
