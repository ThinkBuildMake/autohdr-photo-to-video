import os

import pytest

from app.config import reset_settings
from app.providers import interface
from app.shared.types import ClipResult
from tests.providers.video.conftest import CLIP_BYTES


@pytest.fixture
def real_providers(monkeypatch, videos_api):
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    reset_settings()
    yield videos_api
    monkeypatch.undo()
    reset_settings()


def test_allowed_lengths_reach_the_model_list(real_providers):
    assert interface.allowed_lengths("google/veo-3.1") == [4, 6, 8]


def test_generate_clip_reaches_the_videos_api(real_providers):
    result = interface.generate_clip(b"\xff\xd8jpeg\xff\xd9", "push in", "google/veo-3.1", 4.0, {})

    try:
        assert isinstance(result, ClipResult)
        assert result.seconds == 4
        with open(result.path, "rb") as f:
            assert f.read() == CLIP_BYTES
    finally:
        os.unlink(result.path)
    assert real_providers.count("POST", "/videos") == 1
