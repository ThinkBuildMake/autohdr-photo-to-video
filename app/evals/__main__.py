"""Evals command line: `python -m app.evals import|run|report`. Stub: S14 builds it."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evals")
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("import", help="load the test shoots")
    load.add_argument("--folder", required=True)
    run = sub.add_parser("run", help="run an evaluation suite")
    run.add_argument("--suite", required=True, choices=["ev1", "ev2"])
    run.add_argument("--style", required=True)
    report = sub.add_parser("report", help="write the final report from a filled sheet")
    report.add_argument("--sheet", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("not built yet (S14)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
