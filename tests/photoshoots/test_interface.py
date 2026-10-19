import time

from fastapi.testclient import TestClient

from app.config import reset_settings
from app.main import create_app
from app.photoshoots import labelling, service, stubs
from app.shared.types import Photo
from tests.photoshoots.conftest import jpeg_bytes, seed_shoot, write_jpegs
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE


def _kitchen(monkeypatch):
    monkeypatch.setattr(
        stubs,
        "label_photos",
        lambda photos, shoot_id: [
            {"photoId": p["photoId"], "room": "kitchen", "subject": "kitchen island"}
            for p in photos
        ],
    )


def test_interrupted_labelling_restarts_on_app_start(monkeypatch):
    _kitchen(monkeypatch)
    shoot_id, _ = seed_shoot(["uploaded", "uploaded"], shoot_status="labelling")
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()

    with TestClient(create_app()) as client:
        client.auth = DEMO_AUTH
        deadline = time.monotonic() + 5
        while True:
            shoot = client.get(f"/api/photoshoots/{shoot_id}").json()["photoshoot"]
            if shoot["status"] != "labelling" or time.monotonic() > deadline:
                break
            time.sleep(0.05)

    assert shoot["status"] == "ready"
    assert [p["room"] for p in shoot["photos"]] == ["kitchen", "kitchen"]


def test_list_photos_upload_order(client, monkeypatch):
    _kitchen(monkeypatch)
    files = [{"name": f"{i}.jpg", "size": 1000, "type": "image/jpeg"} for i in range(3)]
    body = client.post("/api/photoshoots", json={"files": files}).json()
    for index in (0, 2):
        stubs.BUCKET[body["uploads"][index]["fields"]["key"]] = jpeg_bytes()
    client.post(f"/api/photoshoots/{body['photoshootId']}/complete")
    labelling.wait_idle()

    photos = service.list_photos(body["photoshootId"])

    assert all(isinstance(p, Photo) for p in photos)
    assert [p.position for p in photos] == [1, 3]
    assert {p.status for p in photos} == {"uploaded"}
    assert {(p.room, p.subject) for p in photos} == {("kitchen", "kitchen island")}


def test_import_photoshoot(client, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(labelling, "start", started.append)
    paths = sorted(write_jpegs(tmp_path, 3))

    shoot_id = service.import_photoshoot(paths, "Test shoot A")

    shoot = client.get(f"/api/photoshoots/{shoot_id}").json()["photoshoot"]
    assert shoot["label"] == "Test shoot A"
    assert [p["status"] for p in shoot["photos"]] == ["uploaded"] * 3
    assert shoot["status"] == "labelling"
    assert len(stubs.BUCKET) == 3
    assert started == [shoot_id]
