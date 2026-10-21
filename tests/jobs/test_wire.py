"""createJob through planJob on the real Library, Photoshoots and Providers."""

import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import reset_settings
from app.db.base import session_scope
from app.jobs import planning
from app.jobs.plan_rules import MOVEMENTS
from app.main import create_app
from app.providers import chat, video_api
from tests.photoshoots.conftest import seed_shoot
from tests.providers.chat.conftest import BASE, TEST_KEY, _chat_answer
from tests.providers.video.conftest import MODEL_LIST
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE
from tests.support.stub_data import STUB_SONG_ID

STYLE = "Slow dolly through the rooms."


def _shot(photo_id: str, length: float = 4) -> dict:
    return {
        "room": "living",
        "photoId": photo_id,
        "photoEditPrompts": [],
        "movementName": "dolly_in",
        "movementPrompt": MOVEMENTS["dolly_in"],
        "speed": "slow",
        "model": "google/veo-3.1",
        "lengthS": length,
        "transition": "cut",
        "transitionS": 0,
        "planNote": "From the photos.",
    }


class _OpenRouter:
    def __init__(self, answer):
        self.answer = answer
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/videos/models"):
            return httpx.Response(200, json=MODEL_LIST)
        self.requests.append(request)
        content = self.answer(request) if callable(self.answer) else self.answer
        return httpx.Response(200, json=_chat_answer(content))


def _app(monkeypatch, openrouter: _OpenRouter):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    chat.reset_pricing()
    video_api.reset_cache()
    transport = httpx.MockTransport(openrouter.handler)
    monkeypatch.setattr(chat, "TRANSPORT", transport)
    monkeypatch.setattr(video_api, "TRANSPORT", transport)
    return create_app()


def _uploaded_shoot():
    shoot_id, photo_ids = seed_shoot(
        ["uploaded", "awaiting_upload", "uploaded"], shoot_status="ready"
    )
    return shoot_id, [photo_ids[0], photo_ids[2]]


def _plan_text(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return "\n".join(
        part.get("text", "")
        for part in body["messages"][0]["content"]
        if isinstance(part, dict) and part.get("type") == "text"
    )


def _photo_ids(request: httpx.Request) -> list[str]:
    return [
        line.split(";", 1)[0].removeprefix("photoId: ").strip()
        for line in _plan_text(request).splitlines()
        if line.startswith("photoId: ")
    ]


def test_create_job_plans_through_library_photos_and_openrouter(
    _isolated_environment, bucket, stub_presets, monkeypatch
):
    shoot_id, uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(
        lambda request: json.dumps(
            {"shots": [_shot(photo_id) for photo_id in _photo_ids(request)], "notes": ""}
        )
    )
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        assert created.status_code == 201
        job_id = created.json()["job"]["id"]
        planning.wait_idle()
        job = client.get(f"/api/jobs/{job_id}").json()["job"]

    with session_scope() as session:
        rows = session.execute(text("select kind, status from provider_calls")).all()
    assert rows == [("plan_shots", "ok")]
    assert [shot["photoId"] for shot in job["shots"]] == uploaded
    request_text = _plan_text(openrouter.requests[0])
    for photo_id in uploaded:
        assert f"photoId: {photo_id}" in request_text


def _lengths_then(lengths: list[float]):
    pending = list(lengths)

    def answer(request: httpx.Request) -> str:
        length = pending.pop(0)
        shots = [_shot(photo_id, length) for photo_id in _photo_ids(request)]
        return json.dumps({"shots": shots, "notes": ""})

    return answer


def test_invalid_plan_is_asked_once_then_fails(
    _isolated_environment, bucket, stub_presets, monkeypatch
):
    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(_lengths_then([3, 4]))
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        job_id = created.json()["job"]["id"]
        planning.wait_idle()
        job = client.get(f"/api/jobs/{job_id}").json()["job"]

    assert job["planStatus"] == "ready"
    assert len(openrouter.requests) == 2
    assert "Your last plan was refused" in _plan_text(openrouter.requests[1])

    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(_lengths_then([3, 3]))
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        job_id = created.json()["job"]["id"]
        planning.wait_idle()
        failed = client.get(f"/api/jobs/{job_id}").json()["job"]

    assert failed["planStatus"] == "failed"


def test_missing_style_is_404(_isolated_environment, bucket, stub_presets, monkeypatch):
    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(lambda _request: "{}")
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        response = client.post(
            "/api/jobs",
            json={
                "photoshootId": shoot_id,
                "styleText": STYLE,
                "songId": STUB_SONG_ID,
                "styleId": "00000000-0000-4000-8000-000000000000",
            },
        )

    assert response.status_code == 404
    assert response.json()["error"] == "style_not_found"
    with session_scope() as session:
        count = session.scalar(text("select count(*) from provider_calls"))
    assert count == 0


def test_planner_bad_response_twice_fails_the_plan(
    _isolated_environment, bucket, stub_presets, monkeypatch
):
    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(lambda _request: json.dumps({"notes": "no shots here"}))
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        job_id = created.json()["job"]["id"]
        planning.wait_idle()
        job = client.get(f"/api/jobs/{job_id}").json()["job"]

    assert job["planStatus"] == "failed"
    assert job["planNotes"]


def test_one_shots_edit_leaves_the_other_stored(
    _isolated_environment, bucket, stub_presets, monkeypatch
):
    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(
        lambda request: json.dumps(
            {"shots": [_shot(photo_id) for photo_id in _photo_ids(request)], "notes": ""}
        )
    )
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        job_id = created.json()["job"]["id"]
        planning.wait_idle()
        shots = client.get(f"/api/jobs/{job_id}").json()["job"]["shots"]
        untouched = {
            "photoId": shots[1]["photoId"],
            "lengthS": shots[1]["lengthS"],
            "movementName": shots[1]["movementName"],
        }
        shots[0]["movementName"] = "crane_up"
        saved = client.put(f"/api/jobs/{job_id}/shots", json={"shots": shots})
        assert saved.status_code == 200
        second = client.get(f"/api/jobs/{job_id}").json()["job"]["shots"][1]

    assert second["photoId"] == untouched["photoId"]
    assert second["lengthS"] == untouched["lengthS"]
    assert second["movementName"] == untouched["movementName"]


def test_plan_request_sends_photos_and_text_not_a_video(
    _isolated_environment, bucket, stub_presets, monkeypatch
):
    shoot_id, _uploaded = _uploaded_shoot()
    openrouter = _OpenRouter(
        lambda request: json.dumps(
            {"shots": [_shot(photo_id) for photo_id in _photo_ids(request)], "notes": ""}
        )
    )
    with TestClient(_app(monkeypatch, openrouter)) as client:
        client.auth = DEMO_AUTH
        created = client.post(
            "/api/jobs",
            json={"photoshootId": shoot_id, "styleText": STYLE, "songId": STUB_SONG_ID},
        )
        assert created.status_code == 201
        planning.wait_idle()
        parts = json.loads(openrouter.requests[0].content)["messages"][0]["content"]
        style = client.post(
            "/api/styles",
            json={
                "name": "No creator video",
                "authorName": "Sam",
                "styleText": "Dark and slow.",
                "songId": STUB_SONG_ID,
                "videoUrl": "https://example.com/creator.mp4",
            },
        )

    assert any(part.get("type") == "image_url" for part in parts)
    assert any(STYLE in part.get("text", "") for part in parts)
    for part in parts:
        assert "video" not in str(part.get("type", "")).lower()
        assert "video" not in str(part.get("filename", "")).lower()
    assert style.status_code == 201
    assert not any("video" in key.lower() for key in style.json()["style"])
