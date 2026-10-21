"""Startup through real Jobs, Providers, Files and app hooks; synthetic persisted work."""

import json
import subprocess
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app import worker
from app.config import reset_settings
from app.files import service as files
from app.jobs import worker_interface
from app.main import create_app
from app.providers import calls, video_api, video_recovery
from tests.providers.video.conftest import MODEL_LIST, VideosApi, completed
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE
from tests.support.library_rows import add_song
from tests.support.worker_rows import (
    add_attempt,
    add_job,
    add_shoot,
    add_shot,
    row,
    set_final_attempt,
)


@pytest.fixture
def startup_world(bucket, monkeypatch, tmp_path):
    monkeypatch.setenv("BYOK_MODELS", "")
    monkeypatch.setenv("FAKE_PROVIDERS", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-startup-key")
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    api = VideosApi()
    clip = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=24:d=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(clip),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    api.clip_bytes = clip.read_bytes()
    api.content = lambda request: httpx.Response(200, content=api.clip_bytes)
    monkeypatch.setattr(video_api, "TRANSPORT", httpx.MockTransport(api.handler))
    monkeypatch.setattr(video_api, "POLL_INTERVAL_S", 0.01)
    video_api.reset_cache()
    song = add_song()
    shoot, photos = add_shoot()
    job = add_job(shoot, song, status="running")
    passed = add_shot(job, 1, photos[0], status="passed")
    passed_attempt = add_attempt(passed, 1, status="passed")
    set_final_attempt(passed, passed_attempt)
    unfinished = add_shot(job, 2, photos[1], status="generating")
    attempt = add_attempt(unfinished, 1, status="running")
    queued = add_job(shoot, song, submitted_at="2026-10-20T00:00:00.000Z")
    yield api, job, passed, unfinished, attempt, queued
    thread = video_recovery._thread
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive(), "Recovery must finish before database teardown"
    video_api.reset_cache()


def start_worker():
    # A shutdown requested before the first claim still runs production startup recovery.
    stop = threading.Event()
    stop.set()
    worker.run(stop)


def test_worker_startup_stops_interrupted_work_and_preserves_finished_and_queued(startup_world):
    api, job, passed, unfinished, attempt, queued = startup_world
    before_passed = row("job_shots", passed)
    before_queued = row("jobs", queued)

    start_worker()

    assert row("jobs", job)["status"] == "stopped"
    assert row("jobs", job)["stop_reason"] == "worker_restarted"
    assert row("attempts", attempt)["status"] == "error"
    assert row("attempts", attempt)["error"] == "worker_restarted"
    assert row("attempts", attempt)["finished_at"] is not None
    assert row("job_shots", unfinished)["status"] == "failed"
    assert row("job_shots", passed) == before_passed
    assert row("jobs", queued) == before_queued
    with TestClient(create_app()) as client:
        response = client.get(f"/api/jobs/{job}", auth=DEMO_AUTH)
        assert response.status_code == 200
        assert response.json()["job"]["stopReason"] == "worker_restarted"
        page = client.get(f"/jobs/{job}", auth=DEMO_AUTH)
        assert page.status_code == 200
        assert "restarted while your video was being made" in page.text
        assert "Start again" in page.text
    settled = row("jobs", job), row("attempts", attempt)
    start_worker()
    assert (row("jobs", job), row("attempts", attempt)) == settled
    assert api.requests == []
    print("Interrupted job: stopped, worker_restarted; open attempt: error; Start again visible")


@pytest.mark.parametrize("pending", [False, True], ids=["completed", "background-poll"])
def test_worker_startup_collects_abandoned_clip_before_closing_call(
    startup_world, tmp_path, pending
):
    api, job, _, unfinished, attempt, _ = startup_world
    call = calls.start_call(
        calls.KIND,
        MODEL_LIST["data"][0]["id"],
        {"jobId": job, "jobShotId": unfinished, "attemptId": attempt},
    )
    calls.set_request_id(call, "job-9")
    api.polls = ([{"id": "job-9", "status": "in_progress"}] if pending else []) + [
        completed(job_id="job-9")
    ]

    start_worker()
    thread = video_recovery._thread
    if pending:
        assert thread is not None
        thread.join(timeout=5)
        assert not thread.is_alive()

    settled = row("provider_calls", call)
    assert settled["status"] == "ok"
    assert settled["finished_at"] is not None
    assert settled["provider_request_id"] == "job-9"
    assert settled["cost_usd"] == 0.8
    path = tmp_path / "collected.mp4"
    files.get(f"clips/recovered/{call}.mp4", str(path))
    assert path.read_bytes() == api.clip_bytes
    assert settled["output_seconds"] == 4
    assert row("job_shots", unfinished)["final_attempt_id"] is None
    assert row("attempts", attempt)["status"] == "error"
    # Start again reuses the paid clip (after the normal check) instead of paying twice.
    offered = worker_interface.run_context(unfinished).recovered
    assert offered.key == f"clips/recovered/{call}.mp4"
    requests = len(api.requests)
    start_worker()
    assert row("provider_calls", call) == settled
    assert len(api.requests) == requests
    print(f"Recovered clips/recovered/{call}.mp4; call=ok; shot remains unapproved")


def test_storage_failure_leaves_paid_clip_collectible_for_next_startup(
    startup_world, monkeypatch, tmp_path
):
    from botocore.exceptions import ClientError

    from app.files.client import get_client

    api, job, _, unfinished, attempt, _ = startup_world
    call = calls.start_call(
        calls.KIND, MODEL_LIST["data"][0]["id"], {"jobId": job, "attemptId": attempt}
    )
    calls.set_request_id(call, "job-9")
    api.polls = [completed(job_id="job-9")]
    monkeypatch.setattr(video_api, "CLIP_TIMEOUT_S", 0)
    s3 = get_client()
    original = s3.upload_file

    def unavailable(*args, **kwargs):
        raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")

    # Fault only the external storage boundary; Files and recovery remain real.
    monkeypatch.setattr(s3, "upload_file", unavailable)
    start_worker()
    thread = video_recovery._thread
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()
    failed_collection = row("provider_calls", call)
    assert failed_collection["status"] == "running"
    assert failed_collection["finished_at"] is None
    assert failed_collection["cost_usd"] == 0.8

    monkeypatch.setattr(s3, "upload_file", original)
    start_worker()

    assert row("provider_calls", call)["status"] == "ok"
    output = tmp_path / "retried.mp4"
    files.get(f"clips/recovered/{call}.mp4", str(output))
    assert output.read_bytes() == api.clip_bytes
    assert row("job_shots", unfinished)["final_attempt_id"] is None


@pytest.mark.parametrize("resume", ["labelling", "planning", "both"])
def test_app_lifespan_resumes_labelling_and_planning_independently(
    startup_world, monkeypatch, resume
):
    from app.jobs import planning
    from app.photoshoots import labelling
    from app.providers import chat
    from tests.providers.chat.conftest import MODELS_JSON, _chat_answer
    from tests.support.jobs_rows import add_draft_job, add_ready_shoot, planned_shot
    from tests.support.worker_rows import rows

    label_shoot, label_photos = add_ready_shoot(
        1, status="labelling" if resume != "planning" else "ready"
    )
    plan_shoot, plan_photos = add_ready_shoot(3)
    job = add_draft_job(
        plan_shoot, add_song(), plan_status="planning" if resume != "labelling" else "ready"
    )
    label_started = threading.Event()
    release_label = threading.Event()
    requested = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS_JSON)
        assert request.url.path.endswith("/chat/completions")
        content = json.loads(request.content)["messages"][0]["content"]
        prompt = " ".join(p.get("text", "") for p in content)
        if "You label real-estate photos" in prompt:
            requested.append("labelling")
            label_started.set()
            assert release_label.wait(timeout=5), "Test must release the labeller"
            answer = {
                "labels": [{"photoId": label_photos[0], "room": "living", "subject": "Blue sofa"}]
            }
        else:
            requested.append("planning")
            answer = {
                "shots": [planned_shot(n, photo) for n, photo in enumerate(plan_photos, 1)],
                "notes": "Resumed synthetic plan",
            }
        return httpx.Response(200, json=_chat_answer(json.dumps(answer)))

    monkeypatch.setattr(chat, "TRANSPORT", httpx.MockTransport(handler))
    chat.reset_pricing()
    try:
        with TestClient(create_app()) as client:
            if resume != "planning":
                assert label_started.wait(timeout=5)
            if resume != "labelling":
                planning.wait_idle(timeout=5)
                response = client.get(f"/api/jobs/{job}", auth=DEMO_AUTH)
                assert response.status_code == 200
                result = response.json()["job"]
                assert result["planStatus"] == "ready", result
                assert [s["photoId"] for s in result["shots"]] == plan_photos
                assert result["planNotes"] == "Resumed synthetic plan"
            if resume == "both":
                # Planning completes while the separate shoot's labeller is still blocked.
                assert row("photoshoots", label_shoot)["status"] == "labelling"
            release_label.set()
            labelling.wait_idle(timeout=5)
            response = client.get(f"/api/photoshoots/{label_shoot}", auth=DEMO_AUTH)
            assert response.status_code == 200
            assert response.json()["photoshoot"]["status"] == "ready"
            if resume != "planning":
                photo = response.json()["photoshoot"]["photos"][0]
                assert (photo["room"], photo["subject"]) == ("living", "Blue sofa")
                labelled = row("photos", label_photos[0])
                assert (labelled["width"], labelled["height"]) == (64, 48)
        assert (
            sorted(requested)
            == {
                "labelling": ["labelling"],
                "planning": ["planning"],
                "both": ["labelling", "planning"],
            }[resume]
        )
        before = rows("select * from provider_calls order by id")
        with TestClient(create_app()):
            labelling.wait_idle(timeout=5)
            planning.wait_idle(timeout=5)
        assert rows("select * from provider_calls order by id") == before
        print(
            f"App lifespan resumed {resume}; API states ready; repeated startup made no new calls"
        )
    finally:
        release_label.set()
        labelling.wait_idle(timeout=5)
        planning.wait_idle(timeout=5)
        chat.reset_pricing()
