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

# Python logging default: "[YYYY-MM-DD HH:MM:SS,ms] LEVEL logger.name: message"
_BRACKETED_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[,.]\d+)?)\]\s+"
    r"(?P<level>[A-Z]{3,8})\s+(?P<source>[\w\.\-]+):\s+(?P<msg>.*)$"
)

# Kubernetes CRI container-log prefix: "<rfc3339> stdout|stderr F|P <inner>"
_K8S_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+"
    r"(?P<stream>stdout|stderr)\s+[FP]\s+(?P<inner>.*)$"
)

# Apache/nginx Combined Log Format.
_APACHE_RE = re.compile(
    r'^(?P<host>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)'
    r'(?:\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)")?\s*$'
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
    # Python logging emits "YYYY-MM-DD HH:MM:SS,ms" — swap comma for dot.
    iso = s.replace("Z", "+00:00").replace(",", ".", 1) if "," in s else s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    # Apache: "28/May/2026:10:32:00 +0000"
    try:
        return datetime.strptime(s, "%d/%b/%Y:%H:%M:%S %z")
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


_STATUS_TO_LEVEL = {"2": "INFO", "3": "INFO", "4": "WARN", "5": "ERROR"}


def _from_apache(m: re.Match, raw: str, seq: int) -> LogRecord:
    status = m.group("status")
    return LogRecord(
        message=m.group("request"),
        seq=seq,
        raw=raw,
        ts=_parse_ts(m.group("ts")),
        level=_STATUS_TO_LEVEL.get(status[:1], "INFO"),
        source=m.group("host"),
        fields={
            "status": status,
            "bytes": m.group("bytes"),
            "ua": m.group("ua") or "",
            "referer": m.group("ref") or "",
        },
    )


def normalize_line(raw: str, seq: int) -> LogRecord:
    line = raw.rstrip("\n")

    # 0. Strip k8s CRI container prefix, then recurse on the inner payload.
    k = _K8S_PREFIX_RE.match(line)
    if k:
        inner = k.group("inner")
        outer_ts = _parse_ts(k.group("ts"))
        stream = k.group("stream")
        inner_record = normalize_line(inner, seq)
        inner_record.raw = raw
        if inner_record.ts is None:
            inner_record.ts = outer_ts
        if inner_record.source is None:
            inner_record.source = stream
        return inner_record

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

    # 3b. Python logging: "[YYYY-MM-DD HH:MM:SS,ms] LEVEL source: msg"
    m = _BRACKETED_RE.match(line)
    if m and m.group("level") in _LEVELS:
        return LogRecord(
            message=m.group("msg"),
            seq=seq,
            raw=raw,
            ts=_parse_ts(m.group("ts")),
            level=m.group("level"),
            source=m.group("source"),
        )

    # 3c. Apache/nginx combined log format
    m = _APACHE_RE.match(line)
    if m:
        return _from_apache(m, raw, seq)

    # 3d. syslog
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


_EXCEPTION_TAIL_RE = re.compile(r"^[\w\.]*[A-Z]\w*(?:Error|Exception|Warning):.+$")


def is_continuation(line: str) -> bool:
    """Heuristic: line continues the previous record.

    Catches indented lines (Python tracebacks, multi-line messages),
    the "Traceback (most recent call last):" header, and the final
    "ExceptionClass: message" tail line — the three pieces of a standard
    Python traceback. Does not falsely merge unrelated log lines.
    """
    if not line:
        return False
    if line[0] in " \t":
        return True
    if line == "Traceback (most recent call last):":
        return True
    return bool(_EXCEPTION_TAIL_RE.match(line))
