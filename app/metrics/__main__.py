"""python -m app.metrics [--sheet SHEET]: print the guarantee metrics from the job tables."""

import argparse
import csv
from pathlib import Path

from app.db.base import session_scope
from app.db.schema import init_db
from app.metrics.report import render_report


def _sheet_job_ids(sheet: Path) -> list[str]:
    with sheet.open(newline="", encoding="utf-8") as handle:
        ids = {row["job_id"] for row in csv.DictReader(handle) if row.get("job_id")}
    return sorted(ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.metrics")
    parser.add_argument("--sheet", type=Path, help="count only the jobs on this reviewer sheet")
    args = parser.parse_args(argv)
    job_ids = _sheet_job_ids(args.sheet) if args.sheet else None
    init_db()
    with session_scope() as session:
        print(render_report(session, job_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
