"""Fixtures for the OpenRouter chat tests: a mocked transport, synthetic pictures, row reader."""

import io
import json
import os

import httpx
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import literal_column, select

from app.config import reset_settings
from app.db.base import session_scope
from app.db.schema import init_db
from app.photoshoots.models import Photoshoot
from app.providers import chat
from app.providers.models import ProviderCall

LIVE_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TEST_KEY = "sk-or-v1-TESTKEY-not-real"
BASE = "https://openrouter.ai/api/v1"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls the real OpenRouter; hand-run only")


def _price(prompt, completion, image_output=None):
    pricing = {"prompt": str(prompt), "completion": str(completion)}
    if image_output is not None:
        pricing["image_output"] = str(image_output)
    return pricing


MODELS_JSON = {
    "data": [
        {"id": "google/gemini-3.8-flash", "pricing": _price(0.000000825, 0.000004125)},
        {"id": "anthropic/claude-sonnet-5.5", "pricing": _price(0.000002, 0.00001)},
        {
            "id": "google/gemini-nano-banana-2.1",
            "pricing": _price(0.0000015, 0.0000075, 0.00003),
        },
        {
            "id": "google/gemini-3.1-flash-image",
            "pricing": _price(0.0000005, 0.000003, 0.00006),
        },
        {"id": "test/byok-chat", "pricing": _price(0.000001, 0.000002)},
    ]
}


class OpenRouterMock:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.model_requests: list[httpx.Request] = []
        self.models_json = json.loads(json.dumps(MODELS_JSON))
        self._queue: list[dict] = []

    def answer(self, status=200, json=None, headers=None, raise_timeout=False):
        self._queue.append(
            {"status": status, "json": json, "headers": headers, "timeout": raise_timeout}
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            self.model_requests.append(request)
            return httpx.Response(200, json=self.models_json)
        self.requests.append(request)
        queued = self._queue.pop(0)
        if queued["timeout"]:
            raise httpx.ReadTimeout("timed out", request=request)
        body = queued["json"]
        if body is None:
            return httpx.Response(queued["status"], headers=queued["headers"], text="not json")
        return httpx.Response(queued["status"], json=body, headers=queued["headers"])

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture
def openrouter(monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", BASE)
    reset_settings()
    init_db()
    with session_scope() as session:
        session.add(Photoshoot(id="ps-1"))
    chat.reset_pricing()
    mock = OpenRouterMock()
    monkeypatch.setattr("app.providers.chat.TRANSPORT", httpx.MockTransport(mock.handler))
    yield mock
    chat.reset_pricing()


@pytest.fixture
def live(monkeypatch):
    if os.environ.get("OPENROUTER_LIVE") != "1" or not LIVE_KEY:
        pytest.skip("live test: set OPENROUTER_LIVE=1 and OPENROUTER_API_KEY")
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", LIVE_KEY)
    reset_settings()
    init_db()
    with session_scope() as session:
        session.add(Photoshoot(id="ps-1"))
    chat.reset_pricing()
    monkeypatch.setattr("app.providers.chat.TRANSPORT", None)
    yield
    chat.reset_pricing()


def make_jpeg(color="gray", text="photo", size=(320, 240)) -> bytes:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, size[0] - 20, size[1] - 20), outline="white", width=4)
    draw.text((40, size[1] // 2), text, fill="white")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def synthetic_jpeg():
    return make_jpeg


def read_rows() -> list[ProviderCall]:
    with session_scope() as session:
        return list(
            session.scalars(
                select(ProviderCall).order_by(ProviderCall.started_at, literal_column("rowid"))
            )
        )


@pytest.fixture
def rows():
    return read_rows


def _chat_answer(content="{}", usage=None, finish_reason="stop", **extra):
    choice = {"finish_reason": finish_reason, "message": {"content": content}, **extra}
    return {"id": "gen-1", "choices": [choice], "usage": usage or {"cost": 0.0021}}


@pytest.fixture
def chat_answer():
    return _chat_answer
