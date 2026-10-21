"""S27 AC1: one real 4 s clip with the production video model. Paid; hand-run only.

OPENROUTER_LIVE=1 uv run --env-file .env pytest tests/providers/video/test_live_clip.py -s
"""

import io
import os

import pytest
from PIL import Image, ImageDraw

from app.config import get_settings, reset_settings
from app.db.schema import init_db
from app.media import video
from app.providers.interface import generate_clip

LIVE_KEY = os.environ.get("OPENROUTER_API_KEY", "")


@pytest.mark.live
def test_live_4s_clip(monkeypatch):
    if os.environ.get("OPENROUTER_LIVE") != "1" or not LIVE_KEY:
        pytest.skip("live test: set OPENROUTER_LIVE=1 and OPENROUTER_API_KEY")
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", LIVE_KEY)
    reset_settings()
    init_db()
    image = Image.new("RGB", (1280, 720), "#d8d2c4")
    ImageDraw.Draw(image).rectangle((200, 150, 1080, 600), outline="white", width=8)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")

    result = generate_clip(
        buffer.getvalue(),
        "Slow, steady push-in toward the centre of the room. No cuts, no people.",
        get_settings().VIDEO_MODEL,
        4,
        {},
    )

    try:
        assert abs(video.probe(result.path)["durationS"] - 4) <= 0.5
    finally:
        os.unlink(result.path)
