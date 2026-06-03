from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime

_ARG_REPR_MAX = 120


@dataclass
class CallEvent:
    qualname: str
    module: str
    filename: str
    lineno: int
    depth: int
    thread_id: int
    t_enter: datetime
    t_exit: datetime | None = None
    args: list[str] | None = None
    task_id: str | None = None


def _safe_repr(value: object) -> str:
    try:
        text = repr(value)
    except Exception:
        text = "<unreprable>"
    if len(text) > _ARG_REPR_MAX:
        text = text[: _ARG_REPR_MAX - 1] + "…"
    return text


class Tracer:
    """Capture the call tree of user code via sys.setprofile, as a context manager.

    Only calls whose code filename starts with one of `include` are recorded, which
    keeps the standard library out and bounds volume. Argument capture is OFF by
    default. Recording stops past `max_events` (sets the `truncated` flag).
    """

    def __init__(
        self,
        include: list[str],
        capture_args: bool = False,
        max_events: int = 100_000,
    ) -> None:
        self.include = tuple(include)
        self.capture_args = capture_args
        self.max_events = max_events
        self.truncated = False
        self._events: list[CallEvent] = []
        self._local = threading.local()
        self._lock = threading.Lock()

    # -- stack is per-thread, so no lock needed for it --
    def _stack(self) -> list[CallEvent]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def _included(self, filename: str) -> bool:
        return filename.startswith(self.include)

    def _current_task_id(self) -> str | None:
        try:
            import asyncio

            task = asyncio.current_task()
        except (RuntimeError, ImportError):
            return None
        return f"task-{id(task)}" if task is not None else None

    def _capture(self, frame) -> list[str]:
        code = frame.f_code
        names = code.co_varnames[: code.co_argcount]
        out: list[str] = []
        for name in names:
            if name in frame.f_locals:
                out.append(f"{name}={_safe_repr(frame.f_locals[name])}")
        return out

    def _hook(self, frame, event, arg):
        if event == "call":
            self._on_call(frame)
        elif event == "return":
            self._on_return(frame)
        # 'c_call'/'c_return' are builtins (no user frame) — intentionally ignored.

    def _on_call(self, frame) -> None:
        code = frame.f_code
        if not self._included(code.co_filename):
            return
        stack = self._stack()
        ev = CallEvent(
            qualname=getattr(code, "co_qualname", code.co_name),
            module=frame.f_globals.get("__name__", "?"),
            filename=code.co_filename,
            lineno=code.co_firstlineno,
            depth=len(stack),
            thread_id=threading.get_ident(),
            t_enter=datetime.now(),
            args=self._capture(frame) if self.capture_args else None,
            task_id=self._current_task_id(),
        )
        stack.append(ev)
        with self._lock:
            if len(self._events) >= self.max_events:
                self.truncated = True
            else:
                self._events.append(ev)

    def _on_return(self, frame) -> None:
        if not self._included(frame.f_code.co_filename):
            return
        stack = self._stack()
        if stack:
            stack.pop().t_exit = datetime.now()

    def __enter__(self) -> "Tracer":
        sys.setprofile(self._hook)
        threading.setprofile(self._hook)
        return self

    def __exit__(self, *exc) -> bool:
        sys.setprofile(None)
        threading.setprofile(None)
        return False

    def events(self) -> list[CallEvent]:
        return list(self._events)
