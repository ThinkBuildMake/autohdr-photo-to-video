"""Evals command line: `python -m app.evals import|run|links|report|all`."""

import argparse
import sys
from pathlib import Path

from app.db.schema import init_db
from app.evals.report import read_sheets, readme_blocker, unreviewed, write_report
from app.evals.runs import SHEET_FILE, relink_sheet, run_suite
from app.evals.shoots import import_shoots
from app.library import service as library

DEFAULT_OUT = "evals/reports"
TIMEOUT_MIN = 480
VIDEOS_PER_PRESET = 2


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
    run.add_argument("--timeout-min", type=float, default=TIMEOUT_MIN)
    links = sub.add_parser("links", help="write the sheet again with fresh video links")
    links.add_argument("--sheet", required=True)
    report = sub.add_parser("report", help="write the final report from filled sheets")
    report.add_argument("--sheet", required=True, action="append")
    report.add_argument("--readme", help="fill this README's results section")
    every = sub.add_parser("all", help="import, run EV-1 and every preset's EV-2 (paid)")
    every.add_argument("--folder", required=True)
    every.add_argument("--out", default=DEFAULT_OUT)
    every.add_argument("--timeout-min", type=float, default=TIMEOUT_MIN)
    every.add_argument("--yes", action="store_true", help="confirm the real, paid jobs")
    return parser


def _all(args) -> int:
    init_db()
    styles = library.list_styles()
    if not styles:
        print("No styles to run: make a style first.")
        return 1
    references = [s.name for s in styles if s.has_reference]
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"No folder {folder}.")
        return 1
    shoots = sum(p.is_dir() for p in folder.iterdir())
    jobs = shoots + VIDEOS_PER_PRESET * len(references)
    if not args.yes:
        per = f"{shoots} EV-1 plus {VIDEOS_PER_PRESET} per preset"
        print(f"This makes {jobs} real, paid jobs ({per}).")
        print("Run again with --yes to start.")
        return 1
    out = Path(args.out)
    import_shoots(folder, out)
    sheets, code = [], 0
    for suite, name in [("ev1", styles[0].name), *[("ev2", n) for n in references]]:
        try:
            sheets.append(run_suite(suite, name, out, args.timeout_min) / SHEET_FILE)
            print(f"reviewer sheet: {sheets[-1]}")
        except SystemExit as stopped:  # a timeout: say so and still run the other suites
            print(stopped.code)
            code = 1
    flags = " ".join(f"--sheet {sheet}" for sheet in sheets)
    print(f"Next: review every video, fill the sheets, then `report {flags} --readme README.md`.")
    return code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import":
        shoots = import_shoots(Path(args.folder), Path(args.out))
        print(f"{len(shoots)} photoshoots in {Path(args.out) / 'shoots.json'}")
    elif args.command == "run":
        folder = run_suite(args.suite, args.style, Path(args.out), args.timeout_min)
        print(f"sheet and report in {folder}")
    elif args.command == "links":
        print(f"sheet with fresh links: {relink_sheet(Path(args.sheet))}")
    elif args.command == "all":
        return _all(args)
    else:
        sheets = [Path(s) for s in args.sheet]
        readme = Path(args.readme) if args.readme else None
        print(f"report in {write_report(sheets, readme)}")
        rows = read_sheets(sheets)
        if blank := unreviewed(rows):
            print(f"{len(blank)} rows are not reviewed yet; fill their marks first.")
            return 2
        if readme and (why := readme_blocker(rows, sheets)):
            print(f"README left as it was: {why}.")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
