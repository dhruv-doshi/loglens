from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import IO, Iterable

from .correlate import Correlator
from .models import Flow, LogRecord, build_flows
from .normalize import normalize_line
from .parser import TemplateParser
from .render import render_flows


def _iter_lines(source: Iterable[str] | str | Path | IO) -> Iterable[str]:
    if isinstance(source, (str, Path)):
        with open(source, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line
        return
    if hasattr(source, "read"):
        for line in source:  # type: ignore[union-attr]
            yield line
        return
    for line in source:
        yield line


class LogLens:
    def __init__(self) -> None:
        self.parser = TemplateParser()
        self.correlator = Correlator()
        self._records: list[LogRecord] = []
        self._seq = 0

    def ingest(self, source: Iterable[str] | str | Path | IO) -> None:
        for raw in _iter_lines(source):
            line = raw.rstrip("\n")
            if not line:
                continue
            record = normalize_line(line, self._seq)
            self.parser.assign(record)
            self._records.append(record)
            self._seq += 1

    def flows(self) -> list[Flow]:
        self.correlator.resolve(self._records)
        return build_flows(self._records)

    def show(self) -> str:
        return render_flows(self.flows())

    def query(self, text: str, top_k: int = 10):
        try:
            from .analyzer import EmbeddingQuery
        except ImportError as e:
            raise RuntimeError(
                "Semantic query requires the 'ai' extra. "
                "Install it with: pip install loglens[ai]"
            ) from e
        analyzer = EmbeddingQuery()
        return analyzer.query(self._records, text, top_k)


class LogLensHandler(logging.Handler):
    def __init__(self, lens: LogLens) -> None:
        super().__init__()
        self.lens = lens

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            r = LogRecord(
                message=message,
                seq=self.lens._seq,
                raw=message,
                ts=datetime.fromtimestamp(record.created),
                level=record.levelname,
                source=record.name,
            )
            self.lens.parser.assign(r)
            self.lens._records.append(r)
            self.lens._seq += 1
        except Exception:
            self.handleError(record)
