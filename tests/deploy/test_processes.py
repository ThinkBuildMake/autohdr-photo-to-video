import os
import random
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    """A currently free port below the kernel's ephemeral range (32768+).

    Binding to port 0 hands out ports from the ephemeral range, which the outgoing
    connections of every concurrent gate run also draw from, so a port found that way
    can be taken again before uvicorn binds it. Ports below the range are only ever
    taken by other listeners, and the fixture retries on a bind failure anyway.
    """
    for _ in range(200):
        port = random.randrange(20000, 32000)
        with socket.socket() as sock:
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                continue
        return port
    pytest.fail("no free port found")


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _become_healthy(proc: subprocess.Popen, port: int) -> bool:
    """Poll /healthz until 200. False if honcho exited first (e.g. the port was taken)."""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=5).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    return False


@pytest.fixture
def honcho(tmp_path):
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    log = tmp_path / "honcho.log"
    for attempt in range(5):
        port = _free_port()
        env = {
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
            "PORT": str(port),
            "FAKE_PROVIDERS": "1",
            "DATABASE_PATH": str(tmp_path / f"app{attempt}.db"),
            "PYTHONUNBUFFERED": "1",
        }
        with log.open("w") as out:
            proc = subprocess.Popen(
                [sys.executable, "-m", "honcho", "-e", str(empty_env), "-f", "Procfile", "start"],
                cwd=ROOT,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        try:
            if _become_healthy(proc, port):
                yield proc, port, log
                return
            exited_early = proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        if not exited_early:
            break  # alive but never healthy: a real failure, not a port clash
    pytest.fail(f"/healthz did not answer 200; honcho output:\n{log.read_text()[-3000:]}")


def _pid(log: Path, process: str) -> int:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        match = re.search(rf"{re.escape(process)} started \(pid=(\d+)\)", log.read_text())
        if match:
            return int(match.group(1))
        time.sleep(0.1)
    pytest.fail(f"no '{process} started' line in honcho's output")


@pytest.mark.parametrize("victim", ["worker.1", "web.1"])
def test_killing_one_process_stops_honcho_and_frees_the_port(honcho, victim):
    proc, port, log = honcho
    pid = _pid(log, victim)

    os.kill(pid, signal.SIGTERM)

    proc.wait(timeout=60)
    assert not _port_open(port)
