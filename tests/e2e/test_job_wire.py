"""Browser evidence through real Jobs reads/writes; no intercepted page or API state."""

import json
import re
import subprocess
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import pytest
from PIL import Image
from playwright.sync_api import expect
from sqlalchemy import text

from app.db.base import session_scope
from app.files import service as files
from app.files.client import get_client
from app.jobs import queue
from app.jobs import worker_interface as worker
from app.pipeline import runner
from app.providers import fake, fake_video
from tests.photoshoots.conftest import seed_shoot
from tests.pipeline.clip_world import flagged_check
from tests.support.library_rows import SOURCE_URL, add_song
from tests.support.queue_rows import add_attempt, add_job, add_shoot, add_shot, set_final_attempt

pytestmark = pytest.mark.e2e


def execute(sql, **params):
    with session_scope() as session:
        session.execute(text(sql), params)


@pytest.fixture
def stored_media(bucket, monkeypatch):
    """Translate bucket signatures to a local HTTP reader of actual moto bucket bytes."""
    client = get_client()

    class Media(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            obj = client.get_object(Bucket=bucket, Key=unquote(parsed.path.lstrip("/")))
            data = obj["Body"].read()
            self.send_response(200)
            self.send_header(
                "Content-Type", "image/png" if parsed.path.endswith(".png") else "video/webm"
            )
            self.send_header("Content-Length", str(len(data)))
            filename = parse_qs(parsed.query).get("attachment")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename[0]}"')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Media)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def sign(key, *, as_attachment=False, filename=None, **kwargs):
        url = f"http://127.0.0.1:{server.server_port}/{quote(key)}"
        return url + (f"?attachment={quote(filename)}" if as_attachment else "")

    monkeypatch.setattr(files, "presign_download", sign)
    yield
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def test_persisted_progress_queue_and_reopen(page, live_server, bucket, tmp_path, monkeypatch):
    fake.reset()
    fake_video.reset()
    song = add_song()
    path = tmp_path / "song.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 6)
    files.put(f"songs/{song}.wav", str(path))
    execute("update songs set file_key=:k where id=:s", k=f"songs/{song}.wav", s=song)
    ids = []
    for label in ("Oak house", "Pine condo"):
        shoot, (photo,) = seed_shoot(["uploaded"], label=label)
        job_id = add_job(shoot, song)
        shot = add_shot(job_id, 1, photo)
        execute("update job_shots set photo_edit_prompts=:p where id=:s", p='["brighten"]', s=shot)
        ids.append(job_id)
    queue.submit_job(ids[0])

    # External provider boundaries hold each persisted stage until the browser has polled it.
    entered = {stage: threading.Event() for stage in ("edit_photo", "generate_clip", "check_clip")}
    release = {stage: threading.Event() for stage in entered}
    for stage in entered:
        original = getattr(fake.FakeProviders, stage)

        def held(self, *args, _stage=stage, _original=original, **kwargs):
            entered[_stage].set()
            if not release[_stage].wait(45):
                raise TimeoutError(f"Browser did not release {_stage}")
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(fake.FakeProviders, stage, held)

    retry_entered, retry_release = threading.Event(), threading.Event()
    generate = fake.FakeProviders.generate_clip
    generations = 0

    def retry_barrier(self, *args, **kwargs):
        nonlocal generations
        generations += 1
        if generations == 2:
            retry_entered.set()
            if not retry_release.wait(45):
                raise TimeoutError("Browser did not release retry")
        return generate(self, *args, **kwargs)

    monkeypatch.setattr(fake.FakeProviders, "generate_clip", retry_barrier)
    fake.answer_on("check_clip", 1, flagged_check())
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(runner.run_next_job)
    try:
        assert entered["edit_photo"].wait(15)
        page.goto(f"{live_server}/jobs/{ids[0]}")
        expect(page.locator("#shot-1 .chip")).to_have_text("Editing the photo")
        queue.submit_job(ids[1])
        assert worker.claim_next_job() is None
        waiting = page.context.new_page()
        waiting.goto(f"{live_server}/jobs/{ids[1]}")
        expect(waiting.get_by_text("Waiting: another video is being made")).to_be_visible()
        expect(waiting.locator(".b-warn")).to_contain_text("Estimated wait:")
        release["edit_photo"].set()
        assert entered["generate_clip"].wait(15)
        expect(page.locator("#shot-1 .chip")).to_have_text("Making the clip", timeout=12000)
        expect(page.locator("#shot-1 .attempts")).to_have_text("Attempts: 1 of 4 this round")
        expect(page.locator("#shot-1")).to_contain_text("Photo edited")
        release["generate_clip"].set()
        assert entered["check_clip"].wait(20)
        expect(page.locator("#shot-1 .chip")).to_have_text("Checking the clip", timeout=12000)
        context = page.context
        page.close()
        reopened = context.new_page()
        reopened.goto(f"{live_server}/jobs")
        reopened.locator(f'a[href="/jobs/{ids[0]}"]').click()
        expect(reopened.locator("#shot-1 .chip")).to_have_text("Checking the clip")
        release["check_clip"].set()
        assert retry_entered.wait(20)
        expect(reopened.locator("#shot-1 .attempts")).to_have_text(
            "Attempts: 2 of 4 this round", timeout=12000
        )
        expect(reopened.locator("#shot-1 .chip")).to_have_text("Trying again")
        retry_release.set()
        assert future.result(timeout=40) is True
        expect(reopened.get_by_text("Your video is ready", exact=True)).to_be_visible(timeout=12000)
        assert worker.claim_next_job().id == ids[1]
        expect(waiting.get_by_text("Making your video: 0 of 1 shots finished")).to_be_visible(
            timeout=12000
        )
        print(
            "AC2 editing -> generating -> checking -> attempt 2 -> ready; "
            "AC3 second shoot waited then ran; AC4 reopened persisted checking via Jobs"
        )
    finally:
        retry_release.set()
        for event in release.values():
            event.set()
        pool.shutdown(wait=True)
        fake.reset()
        fake_video.reset()


def test_persisted_delivery_credit_edits_and_passed_clip(page, live_server, stored_media, tmp_path):
    # VP8 is used because the gate's Chromium does not include an H.264 decoder.
    path = tmp_path / "video.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=24:d=2",
            "-c:v",
            "libvpx",
            str(path),
        ],
        check=True,
    )
    key = "jobs/delivery/video.webm"
    files.put(key, str(path))
    shoot, photos = add_shoot()
    job_id = add_job(
        shoot,
        add_song(),
        status="ready_with_failures",
        video_key=key,
        video_duration_s=2,
        video_width=320,
        video_height=180,
        video_version=1,
    )
    first = add_shot(job_id, 1, photos[0], status="passed")
    add_attempt(first, 1, "flagged", clip_key="jobs/delivery/flagged.mp4")
    passed = add_attempt(first, 2, "passed", clip_key="jobs/delivery/passed.mp4")
    set_final_attempt(first, passed)
    execute("update job_shots set edit_status='edited', model_used='fallback' where id=:i", i=first)
    second = add_shot(
        job_id,
        2,
        photos[1],
        status="failed",
        failure_reason="provider_error",
        status_detail="The service could not generate this room.",
    )
    execute(
        "update job_shots set edit_status='crop_only', "
        "edit_note='The edit changed a window.' where id=:i",
        i=second,
    )

    # Distinct stored images make the original/edited/crop pairing observable in the browser.
    image_path = tmp_path / "frame.png"
    keys = [
        "delivery/original-1.png",
        "delivery/original-2.png",
        "delivery/edited.png",
        "delivery/crop.png",
    ]
    for key, color in zip(keys, ("red", "blue", "green", "yellow"), strict=True):
        Image.new("RGB", (320, 180), color).save(image_path)
        files.put(key, str(image_path))
    for photo, key in zip(photos[:2], keys[:2], strict=True):
        execute("update photos set file_key=:k where id=:i", k=key, i=photo)
    execute("update job_shots set edited_key=:k where id=:i", k=keys[2], i=first)
    execute("update job_shots set cropped_key=:k where id=:i", k=keys[3], i=second)

    page.goto(f"{live_server}/jobs/{job_id}")
    expect(page.locator(".meta")).to_contain_text("12 Oak Street, 3 photos · Style:")
    for position, expected_keys in ((1, (keys[0], keys[2])), (2, (keys[1], keys[3]))):
        images = page.locator(f"#shot-{position} .pair img")
        expect(images).to_have_count(2)
        for index, key in enumerate(expected_keys):
            expect(images.nth(index)).to_have_attribute("src", re.compile(key))
            expect(images.nth(index)).to_be_visible()
            images.nth(index).evaluate(
                "img => img.decode().then(() => { if (!img.naturalWidth) throw Error('empty'); })"
            )
    assert (
        page.locator(".failures").bounding_box()["y"] < page.locator(".player").bounding_box()["y"]
    )
    expect(page.locator(".credit")).to_contain_text("demo use only")
    expect(page.locator(".credit")).to_contain_text("Track A, Artist A, CC BY-NC")
    expect(page.locator(".credit a")).to_have_attribute("href", SOURCE_URL)
    expect(page.locator(".failures")).to_contain_text("The service could not generate this room.")
    expect(page.locator("#shot-1")).to_contain_text("Photo edited")
    expect(page.locator("#shot-1")).to_contain_text("fallback model")
    expect(page.locator("#shot-1 .attempts")).to_have_text("Attempts: 2 of 4 this round")
    expect(page.locator("#shot-2")).to_contain_text("crop only): The edit changed a window.")
    body = page.request.get(f"{live_server}/api/jobs/{job_id}").json()
    assert body["job"]["shots"][0]["clipUrl"].endswith("/passed.mp4")
    assert "flagged.mp4" not in json.dumps(body)
    assert "flagged.mp4" not in page.content()
    video = page.locator("video")
    video.evaluate("v => { v.muted = true; return v.play(); }")
    page.wait_for_function("document.querySelector('video').currentTime > 0.25")
    inline_duration = video.evaluate("v => v.duration")
    with page.expect_download() as info:
        page.get_by_role("link", name="Download video", exact=True).click()
    download = info.value
    assert download.suggested_filename == f"video-{job_id[:8]}-v1.mp4"
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(download.path())]
        )
    )
    downloaded_duration = float(probe["format"]["duration"])
    assert downloaded_duration == pytest.approx(inline_duration, abs=1 / 24)
    assert download.path().read_bytes() == path.read_bytes()
    print(
        f"AC7 Track A / Artist A / BY-NC / {SOURCE_URL}; AC8 only passed clip; "
        f"AC12 edited and crop-only reason; AC13 currentTime advanced, "
        f"inline={inline_duration}s attachment={downloaded_duration}s"
    )
