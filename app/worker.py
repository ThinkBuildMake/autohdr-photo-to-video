"""The worker process: `python -m app.worker`. Runs queued jobs one after another."""

import signal
import threading

from app.db.schema import init_db
from app.pipeline import recovery, runner

IDLE_SLEEP_S = 2.0


def run(stop: threading.Event) -> None:
    init_db()
    recovery.recover_on_start()
    while not stop.is_set():
        if not runner.run_next_job():
            stop.wait(IDLE_SLEEP_S)


def main() -> int:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
