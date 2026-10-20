"""Upload, complete and label across Photoshoots, moto and a mocked OpenRouter."""

import json
import time

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import reset_settings
from app.db.base import session_scope
from app.main import create_app
from app.photoshoots import labelling
from app.providers import chat
from tests.files.test_uploads import post_form
from tests.photoshoots.conftest import jpeg_bytes
from tests.providers.chat.conftest import BASE, TEST_KEY, _chat_answer
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE

ROOMS = ("kitchen", "bedroom", "living")
SUBJECTS = ("white island", "double bed", "sofa")


def _photo_ids(request: httpx.Request) -> list[str]:
    body = json.loads(request.content)
    ids = []
    for part in body["messages"][0]["content"]:
        text_part = part.get("text", "") if isinstance(part, dict) else ""
        if text_part.startswith("photoId: "):
            ids.append(text_part.removeprefix("photoId: ").strip())
    return ids


def _ok(request: httpx.Request) -> httpx.Response:
    labels = [
        {"photoId": photo_id, "room": ROOMS[index], "subject": SUBJECTS[index]}
        for index, photo_id in enumerate(_photo_ids(request))
    ]
    return httpx.Response(200, json=_chat_answer(json.dumps({"labels": labels})))


def _failed(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": {"message": "down"}})


def _upload_three(client) -> str:
    data = jpeg_bytes()
    files = [
        {"name": f"p{index}.jpg", "size": len(data), "type": "image/jpeg"} for index in range(3)
    ]
    created = client.post("/api/photoshoots", json={"label": "Wire", "files": files})
    assert created.status_code == 201
    body = created.json()
    for upload in body["uploads"]:
        assert upload["url"].startswith("https://test-bucket.s3.us-east-1.amazonaws.com/")
        posted = post_form(upload, data, name=upload["name"])
        assert posted.status_code == 204
    return body["photoshootId"]


def _until_settled(client, shoot_id: str) -> dict:
    deadline = time.monotonic() + 15
    shoot = {"status": "labelling"}
    while shoot["status"] == "labelling":
        assert time.monotonic() < deadline
        time.sleep(0.05)
        shoot = client.get(f"/api/photoshoots/{shoot_id}").json()["photoshoot"]
    return shoot


def _run(monkeypatch, handler) -> dict:
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    chat.reset_pricing()
    monkeypatch.setattr(chat, "TRANSPORT", httpx.MockTransport(handler))
    with TestClient(create_app()) as client:
        client.auth = DEMO_AUTH
        try:
            shoot_id = _upload_three(client)
            done = client.post(f"/api/photoshoots/{shoot_id}/complete")
            assert done.status_code == 202
            return _until_settled(client, shoot_id)
        finally:
            labelling.wait_idle()
            chat.reset_pricing()


def test_upload_complete_and_label_on_moto(_isolated_environment, bucket, monkeypatch):
    shoot = _run(monkeypatch, _ok)

    assert shoot["status"] == "ready"
    assert [(photo["room"], photo["subject"]) for photo in shoot["photos"]] == list(
        zip(ROOMS, SUBJECTS, strict=True)
    )
    with session_scope() as session:
        rows = session.execute(text("select kind, status from provider_calls")).all()
    assert rows == [("label_photos", "ok")]


def test_labelling_error_on_mocked_openrouter(_isolated_environment, bucket, monkeypatch):
    shoot = _run(monkeypatch, _failed)

    assert shoot["status"] == "label_failed"
    assert [photo["status"] for photo in shoot["photos"]] == ["uploaded"] * 3
    assert [(photo["room"], photo["subject"]) for photo in shoot["photos"]] == [(None, None)] * 3
