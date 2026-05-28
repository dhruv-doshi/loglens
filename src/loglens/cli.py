from __future__ import annotations

import argparse
import sys

from .lens import LogLens


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="loglens", description="Reconstruct execution flows from logs.")
    ap.add_argument("logfile", help="Path to a log file.")
    ap.add_argument("--query", metavar="TEXT", help="Run semantic query instead of flow view.")
    ap.add_argument("--top-k", type=int, default=10, help="Number of query results (default 10).")
    args = ap.parse_args(argv)

    lens = LogLens()
    lens.ingest(args.logfile)

    if args.query:
        try:
            results = lens.query(args.query, top_k=args.top_k)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        for record, score in results:
            print(f"{score:.3f}\t{record.raw}")
        return 0

    print(lens.show())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
