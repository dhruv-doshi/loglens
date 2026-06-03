from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO, Iterable, Iterator

from .correlate import Correlator
from .models import Flow, LogRecord, _sortable, build_flows
from .normalize import is_continuation, normalize_line
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
        self._traced_flows: list[Flow] = []
        self._seq = 0

    def ingest(self, source: Iterable[str] | str | Path | IO) -> None:
        for raw in _iter_lines(source):
            line = raw.rstrip("\n")
            if not line:
                continue
            if self._records and is_continuation(line):
                prev = self._records[-1]
                prev.message = f"{prev.message}\n{line}"
                prev.raw = f"{prev.raw}\n{line}"
                continue
            record = normalize_line(line, self._seq)
            self.parser.assign(record)
            self._records.append(record)
            self._seq += 1

    def flows(self) -> list[Flow]:
        self.correlator.resolve(self._records)
        # Traced flows are already grouped (trace-NNNN) and must not be
        # re-correlated; merge them in and sort the combined set by start time.
        combined = build_flows(self._records) + list(self._traced_flows)
        combined.sort(key=lambda f: _sortable(f.start_ts))
        return combined

    @contextmanager
    def trace(
        self, include: list[str], capture_args: bool = False
    ) -> Iterator[None]:
        """Run user code under the call tracer; ingest the resulting flows into the
        same store as logs so show()/gaps() work over traced flows too.

        Dev/debug only — sys.setprofile adds overhead; max_events bounds memory.
        """
        from .tracer import Tracer
        from .trace_to_flow import to_flows

        tracer = Tracer(include=include, capture_args=capture_args)
        with tracer:
            yield
        self._traced_flows.extend(to_flows(tracer.events()))

    def show(self, *, color: bool = False, use_template: bool = True) -> str:
        return render_flows(self.flows(), color=color, use_template=use_template)

    def gaps(self) -> dict[str, list]:
        from .gaps import detect_gaps

        return {f.flow_id: detect_gaps(f) for f in self.flows()}

    def check_expectations(self, rules_path: str | Path) -> list:
        from .expectations import check, load_rules

        rules = load_rules(rules_path)
        out: list = []
        for f in self.flows():
            out.extend(check(f, rules))
        return out

    def lineage(self, value: str) -> list[LogRecord]:
        from .lineage import trace

        self.flows()  # ensure flow_id is resolved for display
        return trace(self._records, value)

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
