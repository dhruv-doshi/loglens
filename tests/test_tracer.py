import asyncio
import json
import threading

from loglens.tracer import Tracer
from loglens.trace_to_flow import to_flows

_THIS_FILE = __file__


def _leaf(x):
    return x + 1


def _helper(n):
    return _leaf(n) + _leaf(n)


def _root():
    json.dumps({"k": 1})  # stdlib call — must NOT be recorded
    return _helper(2)


def test_captures_call_tree_with_nesting():
    with Tracer(include=[_THIS_FILE]) as tracer:
        _root()
    events = tracer.events()
    names = [e.qualname for e in events]
    assert "_root" in names
    assert "_helper" in names
    assert "_leaf" in names

    root = next(e for e in events if e.qualname == "_root")
    helper = next(e for e in events if e.qualname == "_helper")
    leaves = [e for e in events if e.qualname == "_leaf"]
    assert root.depth == 0
    assert helper.depth == 1
    assert all(leaf.depth == 2 for leaf in leaves)
    assert len(leaves) == 2


def test_stdlib_calls_are_filtered():
    with Tracer(include=[_THIS_FILE]) as tracer:
        _root()
    assert all("json" not in e.module for e in tracer.events())
    assert all(e.qualname != "dumps" for e in tracer.events())


def test_capture_args_off_by_default():
    with Tracer(include=[_THIS_FILE]) as tracer:
        _leaf(5)
    leaf = next(e for e in tracer.events() if e.qualname == "_leaf")
    assert leaf.args is None


def test_capture_args_on_records_repr():
    with Tracer(include=[_THIS_FILE], capture_args=True) as tracer:
        _leaf(5)
    leaf = next(e for e in tracer.events() if e.qualname == "_leaf")
    assert leaf.args == ["x=5"]


def test_return_sets_t_exit():
    with Tracer(include=[_THIS_FILE]) as tracer:
        _leaf(1)
    leaf = next(e for e in tracer.events() if e.qualname == "_leaf")
    assert leaf.t_exit is not None
    assert leaf.t_exit >= leaf.t_enter


def test_max_events_truncates():
    with Tracer(include=[_THIS_FILE], max_events=1) as tracer:
        _root()
    assert tracer.truncated is True
    assert len(tracer.events()) == 1


def _thread_work(n, barrier):
    barrier.wait()  # ensure both threads are alive at once (distinct idents)
    return _leaf(n)


def test_threads_become_separate_flows():
    barrier = threading.Barrier(2)
    with Tracer(include=[_THIS_FILE]) as tracer:
        threads = [
            threading.Thread(target=_thread_work, args=(i, barrier)) for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    events = tracer.events()
    tids = {e.thread_id for e in events if e.qualname == "_thread_work"}
    assert len(tids) == 2
    flows = to_flows(events)
    work_flows = {
        r.flow_id for f in flows for r in f.records if r.message == "_thread_work"
    }
    assert len(work_flows) == 2


async def _coro(n):
    return _leaf(n)


async def _async_main():
    await asyncio.gather(_coro(1), _coro(2))


def test_async_flows_grouped_by_task_and_labeled_best_effort():
    with Tracer(include=[_THIS_FILE]) as tracer:
        asyncio.run(_async_main())
    events = tracer.events()
    assert any(e.task_id for e in events)

    flows = to_flows(events)
    async_flows = [f for f in flows if "async" in f.origin]
    assert async_flows
    assert all("best-effort" in f.origin for f in async_flows)
    # The two concurrent _coro tasks land in distinct flows.
    coro_flows = {
        r.flow_id for f in flows for r in f.records if r.message == "_coro"
    }
    assert len(coro_flows) == 2
