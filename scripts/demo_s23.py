"""Local S23 demo: FAKE_PROVIDERS=1 .venv/bin/python scripts/demo_s23.py.

Console: credit (third generation since arming), flag SHOT_ID, clear, quit.
Web and worker share the in-memory fake scenarios. No injection HTTP endpoint.
"""

import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    if os.environ.get("FAKE_PROVIDERS") != "1":
        print("This local demo requires FAKE_PROVIDERS=1.", file=sys.stderr)
        return 2
    os.environ["SHOTS_IN_FLIGHT"] = "1"
    import uvicorn

    from app.config import reset_settings
    from app.providers import fake, fake_video
    from app.worker import run

    reset_settings()
    stop = threading.Event()
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=8000))
    worker = threading.Thread(target=run, args=(stop,), daemon=True)
    web = threading.Thread(target=server.run, daemon=True)
    worker.start()
    web.start()
    print("http://127.0.0.1:8000 — commands: credit | flag SHOT_ID | clear | quit")
    try:
        for line in sys.stdin:
            parts = line.split()
            if parts == ["quit"]:
                break
            if parts == ["credit"]:
                fake_video.reset()
                fake_video.fail_on(3, "out_of_credit")
                print("Armed credit failure on generation 3. Submit a new job.")
            elif len(parts) == 2 and parts[0] == "flag":
                fake.flag_shot(parts[1])
                print("Armed repeated flags for", parts[1])
            elif parts == ["clear"]:
                fake.clear()
                fake_video.clear()
                print("Cleared. Start again to resume unfinished shots.")
            else:
                print("Commands: credit | flag SHOT_ID | clear | quit")
    finally:
        stop.set()
        server.should_exit = True
        worker.join(timeout=35)
        web.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
