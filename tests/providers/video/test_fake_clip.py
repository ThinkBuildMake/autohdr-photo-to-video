import io
import json
import os
import subprocess

import pytest
from PIL import Image
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.providers import fake_video, interface
from app.providers.errors import ProviderError


@pytest.fixture(autouse=True)
def _fake_state():
    fake_video.reset()
    init_db()
    yield
    fake_video.reset()


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), (120, 90, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def _rows():
    with session_scope() as session:
        return session.execute(text("SELECT * FROM provider_calls")).mappings().all()


def _probe(path: str) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_type:format=duration", "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def test_fake_generate_clip_makes_a_playable_clip_and_a_cost_zero_row():
    result = interface.generate_clip(_jpeg(), "push in", "google/veo-3.1", 4.0, {})

    try:
        info = _probe(result.path)
        assert info["streams"][0]["codec_type"] == "video"
        assert abs(float(info["format"]["duration"]) - 4.0) <= 0.1
        assert result.seconds == 4.0
        assert result.model == "google/veo-3.1"
    finally:
        os.unlink(result.path)
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["kind"] == "generate_clip"
    assert rows[0]["status"] == "ok"
    assert rows[0]["cost_usd"] == 0
    assert rows[0]["output_seconds"] == 4


def test_fake_generate_clip_error_injection_records_an_error_row():
    fake_video.fail_on(1, "out_of_credit")

    with pytest.raises(ProviderError) as caught:
        interface.generate_clip(_jpeg(), "push in", "google/veo-3.1", 4.0, {})

    assert caught.value.kind == "out_of_credit"
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["error_kind"] == "out_of_credit"


def test_fake_allowed_lengths_for_veo():
    assert interface.allowed_lengths("google/veo-3.1") == [4, 6, 8]
