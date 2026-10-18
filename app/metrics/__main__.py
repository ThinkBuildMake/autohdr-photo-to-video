"""python -m app.metrics: print the guarantee metrics from the job tables."""

from app.db.base import session_scope
from app.db.schema import init_db
from app.metrics.report import render_report


def main() -> int:
    init_db()
    with session_scope() as session:
        print(render_report(session))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
