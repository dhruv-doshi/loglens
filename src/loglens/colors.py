from __future__ import annotations

import os
import sys

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"

_LEVEL_COLOR = {
    "TRACE": DIM,
    "DEBUG": DIM,
    "INFO": GREEN,
    "WARN": YELLOW,
    "WARNING": YELLOW,
    "ERROR": RED,
    "FATAL": RED + BOLD,
    "CRITICAL": RED + BOLD,
}


def should_color(stream=sys.stdout) -> bool:
    """CLI default: color iff stream is a TTY and NO_COLOR is unset."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{RESET}" if enabled and text else text


def level_color(level: str | None) -> str:
    if not level:
        return ""
    return _LEVEL_COLOR.get(level.upper(), "")
