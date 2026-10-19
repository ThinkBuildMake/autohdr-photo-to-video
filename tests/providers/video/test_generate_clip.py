import base64
import logging
import os

import httpx
import pytest
from sqlalchemy import text

from app.config import reset_settings
from app.db.base import session_scope
from app.providers import clip_calls, video_api
from app.providers.errors import ProviderError
from app.providers.video import generate_clip
from tests.providers.video.conftest import API_KEY, CLIP_BYTES, completed

JPEG = b"\xff\xd8\xff\xe0synthetic-jpeg\xff\xd9"


def _rows():
    with session_scope() as session:
        return session.execute(text("SELECT * FROM provider_calls")).mappings().all()


def _call(model="google/veo-3.1", length=4.0):
    return generate_clip(JPEG, "push in", model, length, {})


def test_a_clip_is_made(videos_api):
    result = _call()

    try:
        assert result.seconds == 4
        assert result.model == "google/veo-3.1"
        assert result.cost_usd == 0.8
        assert result.cost_source == "reported"
        assert result.provider_request_id == "job-1"
        with open(result.path, "rb") as f:
            assert f.read() == CLIP_BYTES
    finally:
        os.unlink(result.path)
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["provider_request_id"] == "job-1"


@pytest.mark.parametrize("model", ["google/veo-3.1", "bytedance/seedance-2.0"])
def test_request_asks_for_the_right_format(videos_api, model):
    os.unlink(_call(model).path)

    body = videos_api.submitted()
    assert body["duration"] == 4
    assert body["resolution"] == "1080p"
    assert body["aspect_ratio"] == "16:9"
    assert body["generate_audio"] is False
    frame = body["frame_images"][0]
    assert frame["frame_type"] == "first_frame"
    assert frame["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()


def test_failed_job_is_an_error(videos_api):
    videos_api.polls = [{"id": "job-1", "status": "failed", "error": {"message": "boom"}}]

    with pytest.raises(ProviderError) as caught:
        _call()

    assert caught.value.kind == "failed"
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["error_kind"] == "failed"
    assert rows[0]["finished_at"]


def test_byok_clip_records_list_price(videos_api, monkeypatch):
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1")
    reset_settings()
    videos_api.polls = [completed({"cost": 0, "is_byok": True})]

    result = _call()

    os.unlink(result.path)
    assert result.cost_usd == pytest.approx(0.80)
    assert result.cost_source == "list_price"
    row = _rows()[0]
    assert row["output_seconds"] == 4
    assert row["cost_usd"] == pytest.approx(0.80)
    assert row["cost_source"] == "list_price"


def test_byok_price_lookup_failure_keeps_the_clip(videos_api, monkeypatch):
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1")
    reset_settings()
    videos_api.polls = [completed({"cost": 0, "is_byok": True})]
    videos_api.models = lambda r: httpx.Response(500, json={"error": {"message": "down"}})

    result = _call()

    assert os.path.exists(result.path)
    os.unlink(result.path)
    assert result.cost_usd == pytest.approx(0.80)
    assert result.cost_source == "list_price"
    row = _rows()[0]
    assert row["status"] == "ok"
    assert row["cost_usd"] == pytest.approx(0.80)
    assert row["cost_source"] == "list_price"


def test_byok_model_with_no_listed_or_configured_price_records_zero(videos_api, monkeypatch):
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1")
    monkeypatch.setenv("VIDEO_LIST_PRICES", "")
    reset_settings()
    videos_api.polls = [completed({"cost": 0, "is_byok": True})]
    videos_api.models = lambda r: httpx.Response(500, json={"error": {"message": "down"}})

    result = _call()

    os.unlink(result.path)
    assert result.cost_usd == 0.0
    assert _rows()[0]["status"] == "ok"


def test_out_of_credit_makes_no_second_request(videos_api):
    videos_api.submit = lambda r: httpx.Response(402, json={"error": {"message": "no credit"}})

    with pytest.raises(ProviderError) as caught:
        _call()

    assert caught.value.kind == "out_of_credit"
    assert len(videos_api.requests) == 1
    row = _rows()[0]
    assert row["status"] == "error"
    assert row["error_kind"] == "out_of_credit"


def test_rate_limit_closes_the_row_before_raising(videos_api):
    videos_api.submit = lambda r: httpx.Response(
        429, headers={"Retry-After": "7"}, json={"error": {"message": "slow down"}}
    )

    try:
        _call()
    except ProviderError as error:
        assert error.kind == "rate_limited"
        assert error.retry_after_s == 7.0
        # The row is already closed when the caller sees the error.
        rows = _rows()
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert rows[0]["finished_at"]
    else:
        pytest.fail("expected a ProviderError")
    assert len(videos_api.requests) == 1


def _no_key(value: str) -> bool:
    return API_KEY not in value


def test_key_never_leaks_from_a_failed_submit(videos_api, caplog):
    caplog.set_level(logging.INFO, logger="app")
    videos_api.submit = lambda r: httpx.Response(
        500, json={"error": {"message": f"bad {API_KEY} and Bearer {API_KEY}"}}
    )

    with pytest.raises(ProviderError) as caught:
        _call()

    _assert_clean(videos_api, caught.value, caplog)


def test_key_never_leaks_from_a_failed_job(videos_api, caplog):
    caplog.set_level(logging.INFO, logger="app")
    videos_api.polls = [
        {"id": "job-1", "status": "failed", "error": {"message": f"oops {API_KEY}"}}
    ]

    with pytest.raises(ProviderError) as caught:
        _call()

    _assert_clean(videos_api, caught.value, caplog)


def _assert_clean(api, exc, caplog):
    assert _no_key(str(exc))
    assert _no_key(exc.message)
    assert _no_key(_rows()[0]["error_message"])
    assert _no_key(caplog.text)
    for request in api.requests:
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        assert _no_key(str(request.url))
        assert _no_key(request.content.decode())


@pytest.mark.parametrize("case", ["ok", "402", "429", "500", "poll_failed", "timeout"])
def test_every_call_leaves_exactly_one_priced_row(videos_api, monkeypatch, case):
    if case in ("402", "429", "500"):
        status = int(case)
        videos_api.submit = lambda r: httpx.Response(status, json={"error": {"message": "x"}})
    elif case == "poll_failed":
        videos_api.polls = [{"id": "job-1", "status": "failed"}]
    elif case == "timeout":
        monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
        videos_api.polls = [{"id": "job-1", "status": "in_progress"}]

    try:
        result = _call()
        os.unlink(result.path)
    except ProviderError as error:
        if case == "timeout":
            assert error.kind == "timeout"

    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["cost_usd"] is not None
    assert rows[0]["status"] == ("ok" if case == "ok" else "error")


def test_a_failed_download_keeps_the_paid_clip_recoverable(videos_api):
    videos_api.content = lambda r: httpx.Response(500, json={"error": {"message": "down"}})

    with pytest.raises(ProviderError) as caught:
        _call()

    assert caught.value.kind == "failed"
    (row,) = _rows()
    assert row["status"] == "running"
    assert row["cost_usd"] == 0.8
    assert row["provider_request_id"] == "job-1"
    assert [r[2] for r in clip_calls.open_clip_calls()] == ["job-1"]
