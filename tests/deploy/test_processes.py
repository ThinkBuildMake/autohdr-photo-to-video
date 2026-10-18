import os
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
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def honcho(tmp_path):
    port = _free_port()
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PORT": str(port),
        "FAKE_PROVIDERS": "1",
        "DATABASE_PATH": str(tmp_path / "app.db"),
        "PYTHONUNBUFFERED": "1",
    }
    log = tmp_path / "honcho.log"
    with log.open("w") as out:
        proc = subprocess.Popen(
            [sys.executable, "-m", "honcho", "-e", str(empty_env), "-f", "Procfile", "start"],
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        try:
            yield proc, port, log
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()


def _wait_healthy(port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    pytest.fail("/healthz did not answer 200 within 20 s")


def _pid(log: Path, process: str) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        match = re.search(rf"{re.escape(process)} started \(pid=(\d+)\)", log.read_text())
        if match:
            return int(match.group(1))
        time.sleep(0.1)
    pytest.fail(f"no '{process} started' line in honcho's output")


@pytest.mark.parametrize("victim", ["worker.1", "web.1"])
def test_killing_one_process_stops_honcho_and_frees_the_port(honcho, victim):
    proc, port, log = honcho
    _wait_healthy(port)
    pid = _pid(log, victim)

    os.kill(pid, signal.SIGTERM)

    proc.wait(timeout=15)
    assert not _port_open(port)
