from __future__ import annotations

import json
import re
from datetime import datetime

from .models import LogRecord

_LEVELS = {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"}

_MSG_KEYS = ("msg", "message")
_TS_KEYS = ("ts", "timestamp", "time", "@timestamp")
_LEVEL_KEYS = ("level", "lvl", "severity")
_SOURCE_KEYS = ("source", "logger", "service")

_ISO_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    r"\s+(?P<level>[A-Z]{3,8})\s+(?P<msg>.*)$"
)

_SYSLOG_RE = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<proc>[^:]+):\s+(?P<msg>.*)$"
)

_LEADING_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_LEVEL_TOKEN_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b")

_LOGFMT_RE = re.compile(r'(\w+)=(?:"((?:[^"\\]|\\.)*)"|(\S+))')


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    # ISO-8601 variants
    iso = s.replace("Z", "+00:00")
    # tolerate "YYYY-MM-DD HH:MM:SS"
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    # syslog "%b %d %H:%M:%S" — no year; assume current year
    for fmt in ("%b %d %H:%M:%S", "%b  %d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(year=datetime.now().year)
        except ValueError:
            continue
    return None


def _pick(d: dict, keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    for k in keys:
        if k in d:
            return k, d[k]
    return None, None


def _from_mapping(data: dict, raw: str, seq: int) -> LogRecord:
    fields = dict(data)
    msg_k, msg = _pick(fields, _MSG_KEYS)
    ts_k, ts_v = _pick(fields, _TS_KEYS)
    lvl_k, lvl = _pick(fields, _LEVEL_KEYS)
    src_k, src = _pick(fields, _SOURCE_KEYS)
    for k in (msg_k, ts_k, lvl_k, src_k):
        if k is not None:
            fields.pop(k, None)
    ts = _parse_ts(str(ts_v)) if ts_v is not None else None
    return LogRecord(
        message=str(msg) if msg is not None else "",
        seq=seq,
        raw=raw,
        ts=ts,
        level=str(lvl).upper() if lvl is not None else None,
        source=str(src) if src is not None else None,
        fields=fields,
    )


def _try_json(line: str) -> dict | None:
    s = line.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _try_logfmt(line: str) -> dict | None:
    matches = _LOGFMT_RE.findall(line)
    if not matches:
        return None
    out: dict = {}
    for key, qval, bval in matches:
        out[key] = qval if qval else bval
    # Require at least one of the well-known keys to count as logfmt
    if not (set(out) & set(_MSG_KEYS + _TS_KEYS + _LEVEL_KEYS + _SOURCE_KEYS)):
        return None
    return out


def normalize_line(raw: str, seq: int) -> LogRecord:
    line = raw.rstrip("\n")

    # 1. JSON
    obj = _try_json(line)
    if obj is not None:
        return _from_mapping(obj, raw, seq)

    # 2. logfmt
    obj = _try_logfmt(line)
    if obj is not None:
        return _from_mapping(obj, raw, seq)

    # 3a. ISO-8601 + level + message
    m = _ISO_RE.match(line)
    if m and m.group("level") in _LEVELS:
        return LogRecord(
            message=m.group("msg"),
            seq=seq,
            raw=raw,
            ts=_parse_ts(m.group("ts")),
            level=m.group("level"),
        )

    # 3b. syslog
    m = _SYSLOG_RE.match(line)
    if m:
        return LogRecord(
            message=m.group("msg"),
            seq=seq,
            raw=raw,
            ts=_parse_ts(m.group("ts")),
            source=f"{m.group('host')}/{m.group('proc')}",
        )

    # 4. Fallback
    ts = None
    lt = _LEADING_TS_RE.match(line)
    if lt:
        ts = _parse_ts(lt.group("ts"))
    level = None
    lm = _LEVEL_TOKEN_RE.search(line)
    if lm:
        level = lm.group(1)
    return LogRecord(message=line, seq=seq, raw=raw, ts=ts, level=level)
