"""Fixtures shared by the app, contract and e2e tests."""

import contextlib
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.config import reset_settings
from app.files.client import reset_client
from app.main import create_app

DEMO_PASSPHRASE = "test-pass"
DEMO_AUTH = ("demo", DEMO_PASSPHRASE)


def _bucket_env(monkeypatch) -> None:
    """New video signs a song preview while rendering, so the server needs a bucket name."""
    monkeypatch.setenv("BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("BUCKET_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("BUCKET_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("BUCKET_REGION", "us-east-1")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    _bucket_env(monkeypatch)
    reset_settings()
    reset_client()
    with TestClient(create_app()) as test_client:
        test_client.auth = DEMO_AUTH
        yield test_client


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def serve(app, log_level="warning"):
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level=log_level)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while True:
        try:
            if httpx.get(f"{base_url}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError("live server did not start")
        time.sleep(0.05)
    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    _bucket_env(monkeypatch)
    reset_settings()
    reset_client()
    with serve(create_app()) as base_url:
        yield base_url
