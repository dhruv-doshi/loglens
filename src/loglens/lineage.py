from __future__ import annotations

from .models import LogRecord


def _contains(r: LogRecord, value: str) -> bool:
    needle = value.lower()
    if needle in (r.message or "").lower():
        return True
    return any(needle in str(v).lower() for v in r.fields.values())


def trace(records: list[LogRecord], value: str) -> list[LogRecord]:
    """Return, in original order, every record whose message or field values
    contain `value` — lets the architect follow one entity through the system."""
    return [r for r in records if _contains(r, value)]
