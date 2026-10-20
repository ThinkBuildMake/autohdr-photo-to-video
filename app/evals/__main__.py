"""Evals command line: `python -m app.evals import|run|report`."""

import argparse
import sys
from pathlib import Path

from app.evals.report import write_report
from app.evals.runs import run_suite
from app.evals.shoots import import_shoots

DEFAULT_OUT = "evals/reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evals")
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("import", help="load the test shoots")
    load.add_argument("--folder", required=True)
    load.add_argument("--out", default=DEFAULT_OUT)
    run = sub.add_parser("run", help="run an evaluation suite")
    run.add_argument("--suite", required=True, choices=["ev1", "ev2"])
    run.add_argument("--style", required=True)
    run.add_argument("--out", default=DEFAULT_OUT)
    report = sub.add_parser("report", help="write the final report from a filled sheet")
    report.add_argument("--sheet", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import":
        shoots = import_shoots(Path(args.folder), Path(args.out))
        print(f"{len(shoots)} photoshoots in {Path(args.out) / 'shoots.json'}")
        return 0
    if args.command == "run":
        print(f"sheet and report in {run_suite(args.suite, args.style, Path(args.out))}")
        return 0
    print(f"report in {write_report(Path(args.sheet))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
