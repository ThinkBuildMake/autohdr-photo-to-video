import base64
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings
from app.jobs.stubs import STUB_JOB_ID
from app.main import create_app
from tests.support.fixtures import DEMO_PASSPHRASE, serve


@pytest.fixture
def bare_client(monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_no_credentials_is_401_with_basic_challenge_and_no_body(bare_client):
    response = bare_client.get("/api/styles")

    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.lower().startswith("basic")
    assert "realm=" in challenge
    assert response.content == b""


def test_wrong_passphrase_is_401(bare_client):
    response = bare_client.get("/", auth=("anyone", "wrong"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"].lower().startswith("basic")
    assert response.content == b""


@pytest.mark.parametrize("user", ["anyone", "demo"])
def test_right_passphrase_any_user_name_is_200(bare_client, user):
    response = bare_client.get("/api/styles", auth=(user, DEMO_PASSPHRASE))

    assert response.status_code == 200
    assert "styles" in response.json()


def test_healthz_open_without_credentials(bare_client):
    response = bare_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_passphrase_refuses_everyone_but_healthz(monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", "")
    reset_settings()
    with TestClient(create_app()) as test_client:
        assert test_client.get("/api/styles", auth=("anyone", "")).status_code == 401
        assert test_client.get("/api/styles").status_code == 401
        assert test_client.get("/healthz").status_code == 200


@pytest.mark.parametrize(
    "header", ["Basic !!!", "Bearer x", "Basic " + base64.b64encode(b"nocolon").decode()]
)
def test_malformed_authorization_is_401(bare_client, header):
    response = bare_client.get("/api/styles", headers={"Authorization": header})

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/static/htmx.min.js", "/no/such/path"])
def test_static_and_unknown_paths_need_the_passphrase(bare_client, path):
    assert bare_client.get(path).status_code == 401


def test_passphrase_never_logged(bare_client, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    for password in (DEMO_PASSPHRASE, "wrong"):
        for path in ("/api/styles", "/"):
            bare_client.get(path, auth=("anyone", password))
    with serve(create_app(), log_level="info") as base_url:
        for password in (DEMO_PASSPHRASE, "wrong"):
            httpx.get(f"{base_url}/api/styles", auth=("anyone", password))
    out, err = capfd.readouterr()
    captured = caplog.text + out + err

    assert '"GET /api/styles' in captured
    tokens = [base64.b64encode(f"anyone:{p}".encode()).decode() for p in (DEMO_PASSPHRASE, "wrong")]
    for secret in (DEMO_PASSPHRASE, "wrong", *tokens):
        assert secret not in captured


def test_passphrase_is_the_only_gate_on_paid_jobs(bare_client):
    url = f"/api/jobs/{STUB_JOB_ID}/submit"

    for _ in range(3):
        assert bare_client.post(url, auth=("demo", DEMO_PASSPHRASE)).status_code == 202
    assert bare_client.post(url).status_code == 401
