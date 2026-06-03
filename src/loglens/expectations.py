from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .gaps import Annotation
from .models import Flow, LogRecord


@dataclass
class Rule:
    after: str
    expect_one_of: list[str]
    within_trace: bool = True


def load_rules(path: str | Path) -> list[Rule]:
    """Load a tiny YAML rule list. Each item: after / expect_one_of / within_trace."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    rules: list[Rule] = []
    for item in data:
        rules.append(
            Rule(
                after=str(item["after"]),
                expect_one_of=[str(x) for x in item["expect_one_of"]],
                within_trace=bool(item.get("within_trace", True)),
            )
        )
    return rules


def _text(r: LogRecord) -> str:
    return (r.template or r.message or "").lower()


def _matches_after(r: LogRecord, after: str) -> bool:
    if r.template_id is not None and r.template_id == after:
        return True
    return after.lower() in _text(r)


def check(flow: Flow, rules: list[Rule]) -> list[Annotation]:
    """For each matched 'after' record, flag flows where no expected event follows."""
    out: list[Annotation] = []
    recs = flow.records
    for rule in rules:
        for i, r in enumerate(recs):
            if not _matches_after(r, rule.after):
                continue
            later = recs[i + 1 :]
            satisfied = any(
                any(exp.lower() in _text(x) for exp in rule.expect_one_of)
                for x in later
            )
            if not satisfied:
                expected = ", ".join(rule.expect_one_of)
                out.append(
                    Annotation(
                        flow.flow_id,
                        r.seq,
                        "expectation_violation",
                        f"after '{rule.after}' expected one of [{expected}] but none followed",
                    )
                )
    out.sort(key=lambda a: a.record_seq)
    return out
