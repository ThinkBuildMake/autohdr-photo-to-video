import httpx
import pytest
from sqlalchemy import text

from app.config import reset_settings
from app.db.base import session_scope
from app.providers import clip_calls, video_api, video_recovery
from app.providers.errors import ProviderError
from app.providers.openrouter import OpenRouterProviders
from tests.providers.video.conftest import CLIP_BYTES, completed


@pytest.fixture
def bucket(monkeypatch):
    """Records what recovery puts into the bucket as (key, file bytes)."""
    from app.files import service as files
    from app.media import service as media

    puts: list[tuple[str, bytes]] = []

    def put(key, path):
        with open(path, "rb") as f:
            puts.append((key, f.read()))

    monkeypatch.setattr(files, "put", put)
    monkeypatch.setattr(media, "probe", lambda path: {"durationS": 4.0})
    return puts


def _running(request_id="job-9", model="google/veo-3.1"):
    call_id = clip_calls.start(clip_calls.KIND, model, {})
    if request_id:
        clip_calls.set_request_id(call_id, request_id)
    return call_id


def _row(call_id):
    with session_scope() as session:
        return (
            session.execute(text("SELECT * FROM provider_calls WHERE id = :i"), {"i": call_id})
            .mappings()
            .one()
        )


def test_a_clip_left_running_is_collected_into_the_bucket(videos_api, bucket):
    call_id = _running()
    videos_api.polls = [completed(job_id="job-9")]

    OpenRouterProviders().recover_calls()

    assert bucket == [(f"clips/recovered/{call_id}.mp4", CLIP_BYTES)]
    row = _row(call_id)
    assert row["status"] == "ok"
    assert row["finished_at"] is not None
    assert row["output_seconds"] == 4
    assert row["cost_usd"] == 0.8


def test_a_failed_job_closes_the_row_as_failed(videos_api, bucket):
    call_id = _running()
    videos_api.polls = [{"id": "job-9", "status": "failed", "error": {"message": "boom"}}]

    OpenRouterProviders().recover_calls()

    row = _row(call_id)
    assert row["status"] == "error"
    assert row["error_kind"] == "failed"
    assert row["finished_at"] is not None
    assert bucket == []


def test_a_row_without_a_request_id_is_closed_as_an_error(videos_api, bucket):
    call_id = _running(request_id=None)

    OpenRouterProviders().recover_calls()

    row = _row(call_id)
    assert row["status"] == "error"
    assert row["error_kind"] == "failed"
    assert "restarted" in row["error_message"]
    assert videos_api.requests == []


def test_a_poll_answering_500_does_not_stop_the_worker(videos_api, bucket, monkeypatch):
    call_id = _running()
    other = _running(request_id=None)
    monkeypatch.setattr(
        video_api,
        "poll_job",
        lambda client, job_id: (_ for _ in ()).throw(video_api.http_error(httpx.Response(500))),
    )

    OpenRouterProviders().recover_calls()

    assert _row(call_id)["status"] == "error"
    assert _row(other)["status"] == "error"


def test_an_unreachable_service_does_not_raise_and_keeps_the_row_open(
    videos_api, bucket, monkeypatch
):
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    call_id = _running()
    videos_api.polls = [completed(job_id="job-9")]
    videos_api.content = lambda request: httpx.Response(503, json={"error": {"message": "down"}})

    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()

    row = _row(call_id)
    assert row["status"] == "running"
    assert row["cost_usd"] == 0.8
    assert [r[0] for r in clip_calls.open_clip_calls()] == [call_id]


def test_a_bucket_put_failure_keeps_the_row_open_then_the_next_restart_collects(
    videos_api, bucket, monkeypatch
):
    from app.files import service as files

    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    call_id = _running()
    videos_api.polls = [completed(job_id="job-9")]
    good_put = files.put

    def broken(key, path):
        raise OSError("s3 down")

    monkeypatch.setattr(files, "put", broken)
    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()
    row = _row(call_id)
    assert (row["status"], row["cost_usd"]) == ("running", 0.8)

    monkeypatch.setattr(files, "put", good_put)
    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()
    assert _row(call_id)["status"] == "ok"
    assert bucket == [(f"clips/recovered/{call_id}.mp4", CLIP_BYTES)]


def test_a_probe_failure_still_collects_the_clip(videos_api, bucket, monkeypatch):
    from app.media import service as media

    def broken(path):
        raise RuntimeError("no ffprobe")

    monkeypatch.setattr(media, "probe", broken)
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1")
    reset_settings()
    call_id = _running()
    videos_api.polls = [completed(job_id="job-9", usage={"is_byok": True})]

    OpenRouterProviders().recover_calls()

    row = _row(call_id)
    assert row["status"] == "ok"
    assert row["output_seconds"] is None
    assert row["cost_usd"] == 0.0
    assert row["cost_source"] == "list_price"
    assert len(bucket) == 1


def test_a_still_running_job_is_polled_in_the_background_until_done(videos_api, bucket):
    call_id = _running()
    videos_api.polls = [
        {"id": "job-9", "status": "in_progress"},
        {"id": "job-9", "status": "in_progress"},
        completed(job_id="job-9"),
    ]

    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()

    assert _row(call_id)["status"] == "ok"
    assert bucket == [(f"clips/recovered/{call_id}.mp4", CLIP_BYTES)]


def test_a_job_that_never_finishes_is_closed_as_timeout(videos_api, bucket, monkeypatch):
    call_id = _running()
    videos_api.polls = [{"id": "job-9", "status": "in_progress"}]
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)

    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()

    row = _row(call_id)
    assert row["status"] == "error"
    assert row["error_kind"] == "timeout"


def _byok(monkeypatch):
    monkeypatch.setenv("BYOK_MODELS", "google/veo-3.1")
    reset_settings()


def _generate_with_content_500(videos_api):
    from tests.providers.video.test_generate_clip import _call

    videos_api.polls = [completed({"cost": 0, "is_byok": True})]
    videos_api.content = lambda r: httpx.Response(500, json={"error": {"message": "down"}})
    with pytest.raises(ProviderError):
        _call()
    (call_id,) = [r[0] for r in clip_calls.open_clip_calls()]
    assert (_row(call_id)["cost_usd"], _row(call_id)["output_seconds"]) == (0.8, 4)
    return call_id


def test_recovery_never_lowers_the_byok_cost_when_the_download_keeps_failing(
    videos_api, bucket, monkeypatch
):
    _byok(monkeypatch)
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    call_id = _generate_with_content_500(videos_api)
    videos_api.polls = [completed(job_id="job-1", usage={"cost": 0, "is_byok": True})]

    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()

    row = _row(call_id)
    assert row["status"] == "running"
    assert (row["cost_usd"], row["cost_source"]) == (0.8, "list_price")


def test_recovery_keeps_the_byok_cost_when_the_probe_fails(videos_api, bucket, monkeypatch):
    from app.media import service as media

    _byok(monkeypatch)
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    call_id = _generate_with_content_500(videos_api)
    videos_api.polls = [completed(job_id="job-1", usage={"cost": 0, "is_byok": True})]
    videos_api.content = lambda r: httpx.Response(200, content=CLIP_BYTES)

    def broken(path):
        raise RuntimeError("no ffprobe")

    monkeypatch.setattr(media, "probe", broken)
    OpenRouterProviders().recover_calls()

    row = _row(call_id)
    assert row["status"] == "ok"
    assert (row["cost_usd"], row["cost_source"], row["output_seconds"]) == (0.8, "list_price", 4)


def test_a_permanent_404_on_the_content_closes_the_row_as_failed_with_its_cost(
    videos_api, bucket, monkeypatch
):
    from tests.providers.video.test_generate_clip import _call

    _byok(monkeypatch)
    videos_api.polls = [completed({"cost": 0, "is_byok": True})]
    videos_api.content = lambda r: httpx.Response(404, json={"error": {"message": "gone"}})

    with pytest.raises(ProviderError) as caught:
        _call()

    assert caught.value.kind == "failed"
    assert clip_calls.open_clip_calls() == []
    with session_scope() as session:
        row = session.execute(text("SELECT * FROM provider_calls")).mappings().one()
    assert (row["status"], row["error_kind"], row["cost_usd"]) == ("error", "failed", 0.8)
    assert row["error_message"] == "The clip finished but could not be downloaded."
    assert row["finished_at"] is not None


def test_recovery_closes_a_row_whose_content_is_gone_for_good(videos_api, bucket, monkeypatch):
    _byok(monkeypatch)
    call_id = _generate_with_content_500(videos_api)
    videos_api.polls = [completed(job_id="job-1", usage={"cost": 0, "is_byok": True})]
    videos_api.content = lambda r: httpx.Response(410, json={"error": {"message": "gone"}})

    OpenRouterProviders().recover_calls()

    row = _row(call_id)
    assert (row["status"], row["error_kind"], row["cost_usd"]) == ("error", "failed", 0.8)
    assert row["error_message"] == "The clip finished but could not be downloaded."
    assert row["finished_at"] is not None


def test_a_row_past_the_collect_window_is_closed_on_recovery(videos_api, bucket, monkeypatch):
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    call_id = _running()
    videos_api.polls = [completed(job_id="job-9")]
    videos_api.content = lambda request: httpx.Response(503, json={"error": {"message": "down"}})

    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()
    assert _row(call_id)["status"] == "running"  # inside the window: kept

    with session_scope() as session:
        session.execute(
            text("UPDATE provider_calls SET started_at = '2020-01-01T00:00:00.000Z' WHERE id = :i"),
            {"i": call_id},
        )
    OpenRouterProviders().recover_calls()
    video_recovery.wait_for_background()

    row = _row(call_id)
    assert (row["status"], row["error_kind"], row["cost_usd"]) == ("error", "failed", 0.8)
    assert row["error_message"] == "The clip finished but could not be downloaded."
    assert row["finished_at"] is not None


def test_the_collect_window_defaults_to_24_hours(monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("CLIP_COLLECT_WINDOW_HOURS", raising=False)
    reset_settings()
    assert get_settings().CLIP_COLLECT_WINDOW_HOURS == 24
