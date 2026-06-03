from __future__ import annotations

from .models import Flow, LogRecord, build_flows
from .tracer import CallEvent

_TRACE_ORIGIN = "trace"
# Coroutines interleave on one thread; even grouped by task they can't be cleanly
# separated, so we label them honestly — mirroring synthesized log flows in V1.
_ASYNC_ORIGIN = "trace (async, best-effort)"


def _duration(ev: CallEvent) -> float | None:
    if ev.t_exit is None:
        return None
    return (ev.t_exit - ev.t_enter).total_seconds()


def to_flows(events: list[CallEvent]) -> list[Flow]:
    """Map captured CallEvents to the same Flow object the log pipeline produces,
    so render.py and gaps.py work on traced flows unchanged.

    Grouping:
    - sync calls: by (thread id + outermost call root); each depth-0 call starts a
      new flow id like "trace-0001". Separate threads become separate flows.
    - async calls (task id captured): one flow per asyncio task, labeled
      best-effort because coroutines interleave on a single thread.
    """
    counter = 0
    current: dict[int, str] = {}  # thread_id -> flow_id (sync)
    task_flows: dict[str, str] = {}  # task_id -> flow_id (async)
    origins: dict[str, str] = {}
    records: list[LogRecord] = []

    for i, ev in enumerate(events):
        if ev.task_id is not None:
            if ev.task_id not in task_flows:
                counter += 1
                task_flows[ev.task_id] = f"trace-{counter:04d}"
            fid = task_flows[ev.task_id]
            origins[fid] = _ASYNC_ORIGIN
        else:
            if ev.depth == 0 or ev.thread_id not in current:
                counter += 1
                current[ev.thread_id] = f"trace-{counter:04d}"
            fid = current[ev.thread_id]
            origins.setdefault(fid, _TRACE_ORIGIN)

        records.append(
            LogRecord(
                message=ev.qualname,
                seq=i,
                raw=ev.qualname,
                ts=ev.t_enter,
                source=ev.module,
                template=ev.qualname,
                flow_id=fid,
                flow_origin=origins[fid],
                fields={
                    "depth": ev.depth,
                    "lineno": ev.lineno,
                    "duration": _duration(ev),
                },
            )
        )

    return build_flows(records)
