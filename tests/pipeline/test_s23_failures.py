"""S23 failure journeys through real Jobs/Pipeline/Providers/Files/Media."""

# ruff: noqa: F811

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings
from app.db.base import session_scope
from app.files import service as files
from app.jobs import edits, queue
from app.main import create_app
from app.media import service as media
from app.metrics import queries
from app.metrics.report import render_report
from app.pipeline import runner
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE
from tests.support.s23_world import s23_world  # noqa: F401, F811
from tests.support.worker_rows import rows


def page(job_id, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    with TestClient(create_app()) as client:
        response = client.get(f"/jobs/{job_id}", auth=DEMO_AUTH)
        assert response.status_code == 200
        return response.text


def error_metrics(job_id):
    with session_scope() as session:
        errors = queries.provider_error_delays(session)
        assert errors
        for error in errors:
            assert error["job_id"] == job_id
            assert 0 <= error["delay_s"] < 60
        report = render_report(session)
        for error in errors:
            assert f"call={error['call_id']}" in report
            assert f"attempt={error['attempt_id']}" in report
        print(report)
        return errors


def test_third_generation_credit_stop_is_visible_and_keeps_passed_clips(s23_world, monkeypatch):
    job_id, api = s23_world
    monkeypatch.setenv("SHOTS_IN_FLIGHT", "1")
    reset_settings()
    api.errors["green"] = 402
    queue.submit_job(job_id)
    started = time.monotonic()
    assert runner.run_next_job()
    html = page(job_id, monkeypatch)
    assert time.monotonic() - started < 60
    assert "the video service account is out of credit" in html
    assert "Start again" in html
    print("Stopped: the video service account is out of credit; Start again; shots 1 and 2 kept")
    shots = queue.get_job(job_id).shots
    assert [s.status for s in shots[:2]] == ["passed", "passed"]
    assert all(s.clip_url for s in shots[:2])
    assert api.generations == {"red": 1, "blue": 1, "green": 1}
    before = error_metrics(job_id)
    edits.restart_job(job_id)
    assert error_metrics(job_id) == before


def test_flags_leave_playable_partial_video_and_reason(s23_world, monkeypatch, tmp_path):
    job_id, api = s23_world
    api.flagged.add("green")
    queue.submit_job(job_id)
    assert runner.run_next_job()
    html = page(job_id, monkeypatch)
    assert "flagged every attempt" in html
    assert "Synthetic flagged clip" in html
    print("Shot 3: flagged every attempt; Synthetic flagged clip; player available")
    assert "<video controls" in html
    job = queue.get_job(job_id)
    assert job.status == "ready_with_failures"
    assert job.shots[2].attempts == 4
    assert api.generations == {"red": 1, "blue": 1, "green": 4, "yellow": 1}
    key = rows("select video_key from jobs where id=:j", j=job_id)[0]["video_key"]
    output = str(tmp_path / "partial.mp4")
    files.get(key, output)
    assert media.probe(output)["durationS"] == pytest.approx(12, abs=1 / 24)
    pixels = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            output,
            "-vf",
            "scale=1:1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    palette = {
        "red": (255, 0, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "green": (0, 128, 0),
    }
    colors = [
        min(
            palette,
            key=lambda c: sum(
                (a - b) ** 2 for a, b in zip(pixels[i : i + 3], palette[c], strict=True)
            ),
        )
        for i in range(0, len(pixels), 3)
    ]
    assert colors == ["red"] * 96 + ["blue"] * 96 + ["yellow"] * 96
    print("Partial video: 12 seconds; red, blue, yellow; green excluded after four flags")


def test_rate_limit_is_visible_before_retry_returns(s23_world, monkeypatch):
    job_id, api = s23_world
    api.errors["blue"] = 429
    api.pause_retry = True
    queue.submit_job(job_id)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runner.run_next_job)
        try:
            assert api.retry_entered.wait(20)
            started = api.error_at["blue"]
            html = page(job_id, monkeypatch)
            assert "provider busy" in html.lower()
            assert time.monotonic() - started < 60
            error_metrics(job_id)
        finally:
            api.release_retry.set()
        assert future.result(timeout=60)
    assert queue.get_job(job_id).status == "ready"


def test_refusal_isolated_to_one_shot(s23_world, monkeypatch):
    job_id, api = s23_world
    api.errors["green"] = 403
    queue.submit_job(job_id)
    api.hold_color = "yellow"
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runner.run_next_job)
        try:
            assert api.held.wait(20)
            deadline = time.monotonic() + 20
            while queue.get_job(job_id).shots[2].status != "failed":
                assert time.monotonic() < deadline
                time.sleep(0.02)
            html = page(job_id, monkeypatch)
            assert "refused this shot" in html
            assert time.monotonic() - api.error_at["green"] < 60
            assert queue.get_job(job_id).status == "running"
        finally:
            api.release.set()
        assert future.result(timeout=60)
    job = queue.get_job(job_id)
    assert job.status == "ready_with_failures"
    assert job.shots[2].failure_reason == "refused"
    assert all(s.status == "passed" for s in job.shots if s.position != 3)
    assert "refused this shot" in page(job_id, monkeypatch)
    error_metrics(job_id)
