import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings
from app.main import create_app
from app.photoshoots import labelling
from tests.photoshoots.conftest import jpeg_bytes, put_bytes, seed_shoot
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE

PHOTO_KEYS = {
    "id", "position", "originalName", "contentType", "sizeBytes", "status", "room", "subject",
    "thumbUrl",
}  # fmt: skip


@pytest.fixture
def client(_isolated_environment, bucket, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    with TestClient(create_app()) as test_client:
        test_client.auth = DEMO_AUTH
        yield test_client
    labelling.wait_idle()


def _file(name="a.jpg", size=1000, type_="image/jpeg"):
    return {"name": name, "size": size, "type": type_}


def test_create_upload(client):
    response = client.post("/api/photoshoots", json={"label": "Shoot", "files": [_file()]})

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"photoshootId", "uploads", "refused"}
    assert set(body["uploads"][0]) == {"photoId", "name", "url", "fields"}
    assert body["refused"] == []


def test_create_upload_refuses_wrong_type_and_too_large(client):
    files = [_file(), _file("b.gif", type_="image/gif"), _file("c.jpg", size=26_214_401)]

    body = client.post("/api/photoshoots", json={"files": files}).json()

    assert [u["name"] for u in body["uploads"]] == ["a.jpg"]
    assert body["refused"] == [
        {"name": "b.gif", "reason": "wrong_type"},
        {"name": "c.jpg", "reason": "too_large"},
    ]


def test_create_upload_too_many_files(client):
    response = client.post(
        "/api/photoshoots", json={"files": [_file(f"{i}.jpg") for i in range(41)]}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "too_many_files"


def test_create_upload_no_valid_files(client):
    response = client.post("/api/photoshoots", json={"files": [_file("a.gif", type_="image/gif")]})

    assert response.status_code == 400
    assert response.json()["error"] == "no_valid_files"


def _shoot(client):
    body = client.post("/api/photoshoots", json={"files": [_file()]}).json()
    put_bytes(body["uploads"][0]["fields"]["key"], jpeg_bytes())
    return body["photoshootId"]


def test_complete_upload(client):
    response = client.post(f"/api/photoshoots/{_shoot(client)}/complete")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"photoshoot"}
    assert set(body["photoshoot"]) == {"id", "status", "photos"}
    assert set(body["photoshoot"]["photos"][0]) == PHOTO_KEYS


def test_get_photoshoot(client):
    response = client.get(f"/api/photoshoots/{_shoot(client)}")

    body = response.json()
    assert response.status_code == 200
    assert set(body["photoshoot"]) == {"id", "label", "status", "photos"}
    assert set(body["photoshoot"]["photos"][0]) == PHOTO_KEYS


def test_list_photoshoots(client):
    shoot_id, _ = seed_shoot(["uploaded", "uploaded", "missing"], "ready", label="Test shoot A")

    response = client.get("/api/photoshoots")

    assert response.status_code == 200
    assert response.json() == {"photoshoots": [{"id": shoot_id, "label": "Test shoot A"}]}


def test_unknown_photoshoot(client):
    response = client.get("/api/photoshoots/nope")

    assert response.status_code == 404
    assert response.json()["error"] == "photoshoot_not_found"
