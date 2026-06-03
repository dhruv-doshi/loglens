from __future__ import annotations

import argparse
import os
import runpy
import sys

from . import __version__
from .colors import should_color
from .lens import LogLens
from .render import (
    format_query_result,
    render_annotations,
    render_flows_json,
    render_flows_mermaid,
    render_lineage,
)


def _resolve_color(args) -> bool:
    if args.no_color:
        return False
    if args.color:
        return True
    return should_color(sys.stdout)


def _trace_main(argv: list[str] | None) -> int:
    ap = argparse.ArgumentParser(
        prog="loglens trace",
        description="Run a module under the call tracer and print its flow tree.",
    )
    ap.add_argument("-m", "--module", required=True, help="Module to import and run.")
    ap.add_argument(
        "--include",
        action="append",
        metavar="PREFIX",
        help="Path prefix(es) to record (default: current working directory).",
    )
    ap.add_argument("--capture-args", action="store_true", help="Record repr() of call args.")
    color_group = ap.add_mutually_exclusive_group()
    color_group.add_argument("--color", action="store_true", help="Force ANSI color output.")
    color_group.add_argument("--no-color", action="store_true", help="Disable ANSI color output.")
    args = ap.parse_args(argv)

    color = _resolve_color(args)
    include = args.include or [os.getcwd()]
    lens = LogLens()
    with lens.trace(include=include, capture_args=args.capture_args):
        runpy.run_module(args.module, run_name="__main__")
    print(lens.show(color=color))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] == "trace":
        return _trace_main(raw[1:])

    ap = argparse.ArgumentParser(prog="loglens", description="Reconstruct execution flows from logs.")
    ap.add_argument("--version", action="version", version=f"loglens {__version__}")
    ap.add_argument("logfile", help="Path to a log file.")
    ap.add_argument("--query", metavar="TEXT", help="Run semantic query instead of flow view.")
    ap.add_argument("--top-k", type=int, default=10, help="Number of query results (default 10).")
    ap.add_argument("--gaps", action="store_true", help="Show structural anomalies per flow.")
    ap.add_argument("--expect", metavar="RULES.yaml", help="Check declared expectation rules.")
    ap.add_argument("--lineage", metavar="VALUE", help="Follow one value across all flows.")
    ap.add_argument("--json", action="store_true", help="Render flows as JSON.")
    ap.add_argument("--mermaid", action="store_true", help="Render flows as a Mermaid flowchart.")
    ap.add_argument("--no-template", action="store_true", help="Show raw messages instead of mined templates.")
    color_group = ap.add_mutually_exclusive_group()
    color_group.add_argument("--color", action="store_true", help="Force ANSI color output.")
    color_group.add_argument("--no-color", action="store_true", help="Disable ANSI color output.")
    args = ap.parse_args(raw)

    color = _resolve_color(args)

    lens = LogLens()
    lens.ingest(args.logfile)

    if args.query:
        try:
            results = lens.query(args.query, top_k=args.top_k)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        for record, score in results:
            print(format_query_result(record, score, color=color))
        return 0

    if args.gaps:
        annotations = [a for anns in lens.gaps().values() for a in anns]
        print(render_annotations(annotations, color=color))
        return 0

    if args.expect:
        print(render_annotations(lens.check_expectations(args.expect), color=color))
        return 0

    if args.lineage:
        print(render_lineage(lens.lineage(args.lineage), color=color))
        return 0

    if args.json:
        print(render_flows_json(lens.flows()))
        return 0

    if args.mermaid:
        print(render_flows_mermaid(lens.flows()))
        return 0

    print(lens.show(color=color, use_template=not args.no_template))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
