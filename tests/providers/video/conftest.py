import json

import httpx
import pytest

from app.config import reset_settings
from app.db.schema import init_db
from app.providers import video_api

API_KEY = "sk-or-v1-test0123456789abcdef"
BASE = "https://openrouter.ai/api/v1"
CLIP_BYTES = b"synthetic-mp4-bytes" * 50

MODEL_LIST = {
    "data": [
        {
            "id": "google/veo-3.1",
            "supported_durations": [4, 6, 8],
            "pricing_skus": {"duration_seconds_without_audio": "0.20"},
        },
        {
            "id": "bytedance/seedance-2.0",
            "supported_durations": list(range(4, 16)),
            "pricing_skus": {"video_tokens_1080p": "0.0000077"},
        },
    ]
}


def completed(usage=None, job_id="job-1"):
    return {
        "id": job_id,
        "status": "completed",
        "unsigned_urls": [f"{BASE}/videos/{job_id}/content?index=0"],
        "usage": usage if usage is not None else {"cost": 0.8, "is_byok": False},
    }


class VideosApi:
    """Scripted answers for the Videos API; every request is recorded."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.submit = lambda request: httpx.Response(
            200, json={"id": "job-1", "polling_url": f"{BASE}/videos/job-1", "status": "pending"}
        )
        self.polls = [{"id": "job-1", "status": "pending"}, completed()]
        self.models = lambda request: httpx.Response(200, json=MODEL_LIST)
        self.content = lambda request: httpx.Response(200, content=CLIP_BYTES)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v1")
        if request.method == "POST" and path == "/videos":
            return self.submit(request)
        if path == "/videos/models":
            return self.models(request)
        if path.endswith("/content"):
            return self.content(request)
        if path.startswith("/videos/"):
            body = self.polls[0] if len(self.polls) == 1 else self.polls.pop(0)
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    def count(self, method: str, suffix: str) -> int:
        return sum(1 for r in self.requests if r.method == method and r.url.path.endswith(suffix))

    def submitted(self) -> dict:
        post = next(r for r in self.requests if r.method == "POST")
        return json.loads(post.content)


@pytest.fixture
def videos_api(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", API_KEY)
    monkeypatch.setenv("BYOK_MODELS", "")
    reset_settings()
    api = VideosApi()
    monkeypatch.setattr(video_api, "TRANSPORT", httpx.MockTransport(api.handler))
    monkeypatch.setattr(video_api, "POLL_INTERVAL_S", 0)
    video_api.reset_cache()
    init_db()
    yield api
    video_api.reset_cache()
