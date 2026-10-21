"""S23 browser journeys over persisted production state, without stub_jobs."""

# ruff: noqa: F811

import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, urlsplit

import pytest
from playwright.sync_api import expect

from app import worker
from app.config import reset_settings
from app.db.base import session_scope
from app.files import service as files
from app.files.client import get_client
from app.jobs import queue
from app.jobs import worker_interface as jobs_worker
from app.main import create_app
from app.metrics import queries
from app.metrics.report import render_report
from app.pipeline import runner
from tests.pipeline.test_s23_restart_redo_wire import passed_assets
from tests.support.fixtures import DEMO_PASSPHRASE, serve
from tests.support.s23_world import s23_world  # noqa: F401
from tests.support.worker_rows import rows

pytestmark = pytest.mark.e2e


@pytest.fixture
def recovery_server(s23_world, bucket, monkeypatch):
    """Serve real bucket outputs; a VP8 derivative enables codec-limited Chromium playback.

    Downloads remain the original production MP4. No Jobs response or state is replaced.
    """
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    s3 = get_client()
    cache = {}

    class Media(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            key = unquote(parsed.path.lstrip("/"))
            try:
                data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            except s3.exceptions.NoSuchKey:
                self.send_error(404)
                return
            derivative = parsed.query == "play" and key.endswith(".mp4")
            if derivative:
                if key not in cache:
                    with TemporaryDirectory() as folder:
                        source = Path(folder) / "production.mp4"
                        source.write_bytes(data)
                        playable = Path(folder) / "playback.webm"
                        subprocess.run(
                            [
                                "ffmpeg",
                                "-v",
                                "error",
                                "-i",
                                str(source),
                                "-vf",
                                "scale=320:180",
                                "-c:v",
                                "libvpx",
                                "-an",
                                "-f",
                                "webm",
                                str(playable),
                            ],
                            capture_output=True,
                            check=True,
                            timeout=45,
                        )
                        cache[key] = playable.read_bytes()
                data = cache[key]
            self.send_response(200)
            self.send_header(
                "Content-Type", "video/webm" if derivative else "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(data)))
            if parsed.query == "download":
                self.send_header("Content-Disposition", 'attachment; filename="production.mp4"')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Media)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def sign(key, *, as_attachment=False, **kwargs):
        mode = "download" if as_attachment else "play"
        return f"http://127.0.0.1:{server.server_port}/{quote(key)}?{mode}"

    monkeypatch.setattr(files, "presign_download", sign)
    try:
        with serve(create_app()) as url:
            yield url
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def assert_measured_errors(job_id):
    with session_scope() as session:
        errors = queries.provider_error_delays(session)
    assert errors
    assert all(e["job_id"] == job_id and 0 <= e["delay_s"] < 60 for e in errors)
    with session_scope() as session:
        print(render_report(session))


def play_and_download(page, tmp_path):
    video = page.locator(".player video")
    video.evaluate("v => { v.muted = true; return v.play(); }")
    page.wait_for_function("document.querySelector('.player video').currentTime > 0.25")
    with page.expect_download() as download:
        page.get_by_role("link", name="Download video", exact=True).click()
    path = tmp_path / "download.mp4"
    download.value.save_as(path)
    from app.media import service as media

    job_id = urlsplit(page.url).path.rsplit("/", 1)[1]
    key = rows("select video_key from jobs where id=:j", j=job_id)[0]["video_key"]
    original = tmp_path / "stored-original.mp4"
    files.get(key, str(original))
    assert path.read_bytes() == original.read_bytes()
    duration = media.probe(str(path))["durationS"]
    assert duration == pytest.approx(video.evaluate("v => v.duration"), abs=0.1)
    print(f"Real output: playback advanced; original MP4 download matches storage; {duration}s")
    return duration


def test_credit_poll_restart_and_single_shot_redo(
    page, s23_world, recovery_server, bucket, monkeypatch, tmp_path
):
    job_id, api = s23_world
    monkeypatch.setenv("SHOTS_IN_FLIGHT", "1")
    reset_settings()
    api.errors["green"] = 402
    api.hold_color = "green"
    queue.submit_job(job_id)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runner.run_next_job)
        try:
            assert api.held.wait(20)
            page.goto(f"{recovery_server}/jobs/{job_id}")
            expect(page.locator(".b-info")).to_contain_text("Making your video")
            api.release.set()
            assert future.result(timeout=60)
            expect(page.locator(".b-err")).to_contain_text("out of credit", timeout=12000)
            delay = time.monotonic() - api.error_at["green"]
            assert delay < 60
            print(f"Credit error visible after {delay:.3f}s; Start again offered")
        finally:
            api.release.set()
    before = passed_assets(job_id, bucket)
    assert set(before) == {1, 2}
    with session_scope() as session:
        report = render_report(session)
    assert "out_of_credit" in report
    assert_measured_errors(job_id)
    api.errors.clear()
    api.hold_color = None
    page.get_by_role("button", name="Start again", exact=True).click()
    expect(page.locator(".b-warn")).to_contain_text("Waiting to start")
    assert runner.run_next_job()
    expect(page.locator(".player")).to_contain_text("Version 1", timeout=12000)
    assert api.generations == {"red": 1, "blue": 1, "green": 2, "yellow": 1}
    ready = passed_assets(job_id, bucket)
    assert {p: ready[p] for p in before} == before
    assert play_and_download(page, tmp_path) == pytest.approx(16, abs=1 / 24)
    old_src = page.locator(".player video").get_attribute("src")
    page.locator("#shot-2").get_by_role("button", name="Redo this shot").click()
    expect(page.locator(".b-warn")).to_contain_text("Waiting to start")
    assert runner.run_next_job()
    expect(page.locator(".player")).to_contain_text("Version 2", timeout=12000)
    assert page.locator(".player video").get_attribute("src") != old_src
    assert api.generations == {"red": 1, "blue": 2, "green": 2, "yellow": 1}
    after = passed_assets(job_id, bucket)
    assert {p: after[p] for p in (1, 3, 4)} == {p: ready[p] for p in (1, 3, 4)}
    assert after[2][0] == ready[2][0] + 1
    assert play_and_download(page, tmp_path) == pytest.approx(16, abs=1 / 24)
    # A real editor mutation must reject the actual browser redo action in its error slot.
    response = page.request.patch(
        f"{recovery_server}/api/jobs/{job_id}/shots/1", data={"lengthS": 3}
    )
    assert response.status == 200
    page.locator("#shot-2").get_by_role("button", name="Redo this shot").click()
    expect(page.locator(".action-error")).to_have_text(
        "Export your saved edits before redoing a shot."
    )
    assert queue.get_job(job_id).video.version == 2
    print("Version 1 -> 2; only shot 2 redone; pending edit rejected in action error slot")


@pytest.mark.parametrize("failure", ["flags", "refusal", "rate_limit"])
def test_polling_exposes_isolated_failure_before_other_shot_finishes(
    page, s23_world, recovery_server, failure, tmp_path
):
    job_id, api = s23_world
    if failure == "flags":
        api.flagged.add("green")
        message = "flagged every attempt"
    elif failure == "refusal":
        api.errors["green"] = 403
        message = "refused this shot"
    else:
        api.errors["blue"] = 429
        api.pause_retry = True
        message = "provider busy, trying again"
    api.hold_color = "yellow"
    queue.submit_job(job_id)
    page.goto(f"{recovery_server}/jobs/{job_id}")
    expect(page.locator(".b-warn")).to_contain_text("Waiting to start")
    observed_start = time.monotonic()
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runner.run_next_job)
        try:
            assert api.held.wait(20)
            expect(page.locator(".b-info")).to_contain_text("Making your video", timeout=12000)
            started = observed_start
            if failure == "rate_limit":
                assert api.retry_entered.wait(20)
                started = api.error_at["blue"]
            elif failure == "refusal":
                assert api.error_seen.wait(20)
                started = api.error_at["green"]
            shot = page.locator("#shot-2" if failure == "rate_limit" else "#shot-3")
            expect(shot).to_contain_text(message, timeout=15000)
            delay = time.monotonic() - started
            assert delay < 60
            print(f"Shot reason {message!r} visible after {delay:.3f}s while job still running")
            assert queue.get_job(job_id).status == "running"
            if failure != "flags":
                with session_scope() as session:
                    report = render_report(session)
                assert "call=" in report and "attempt=" in report
                assert_measured_errors(job_id)
        finally:
            api.release.set()
            api.release_retry.set()
        assert future.result(timeout=60)
    expect(page.locator(".player")).to_be_visible(timeout=12000)
    if failure != "rate_limit":
        expect(page.locator(".failures")).to_contain_text(message)
        assert play_and_download(page, tmp_path) == pytest.approx(12, abs=1 / 24)
    else:
        assert play_and_download(page, tmp_path) == pytest.approx(16, abs=1 / 24)


def test_worker_recovered_job_explains_restart_and_offers_action(page, s23_world, recovery_server):
    job_id, _ = s23_world
    queue.submit_job(job_id)
    assert jobs_worker.claim_next_job().id == job_id
    stop = threading.Event()
    stop.set()
    worker.run(stop)
    page.goto(f"{recovery_server}/jobs/{job_id}")
    expect(page.locator(".b-err")).to_contain_text("the worker restarted")
    expect(page.get_by_role("button", name="Start again", exact=True)).to_be_visible()
    print("Recovered Job page: the worker restarted; Start again visible")
