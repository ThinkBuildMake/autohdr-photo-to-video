"""Editor browser scenarios through real routes, Jobs, worker and persistent media."""

import re
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest
from playwright.sync_api import expect

from app.files import service as files
from app.jobs import queue
from app.pipeline import runner
from app.providers import fake, fake_video
from tests.e2e import test_job_wire
from tests.e2e.test_editor_page import open_shot, tile_change
from tests.e2e.test_job_wire import execute
from tests.photoshoots.conftest import seed_shoot
from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shot,
    add_song,
    set_final_attempt,
    shot_rows,
)

pytestmark = pytest.mark.e2e
media_server = test_job_wire.stored_media


@pytest.fixture
def editor_job(live_server, media_server, tmp_path):
    fake.reset()
    fake_video.reset()
    shoot, photos = seed_shoot(["uploaded"] * 7, shoot_status="ready")
    for photo, room in zip(photos, ["living"] * 6 + ["kitchen"], strict=True):
        execute("update photos set room=:r where id=:i", r=room, i=photo)
    song = add_song()
    song_path = tmp_path / "song.wav"
    with wave.open(str(song_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 20)
    files.put(f"songs/{song}.wav", str(song_path))
    execute("update songs set file_key=:k where id=:i", k=f"songs/{song}.wav", i=song)
    clip = tmp_path / "clip.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=24:d=4",
            "-c:v",
            "libvpx",
            str(clip),
        ],
        check=True,
    )
    job = add_job(
        shoot,
        song,
        status="ready",
        submitted_at="2026-10-19T08:00:00.000Z",
        video_key="editor/old.webm",
        video_version=1,
        video_duration_s=18,
        video_width=320,
        video_height=180,
    )
    files.put("editor/old.webm", str(clip))
    for pos, photo in enumerate(photos[:6], 1):
        shot = add_shot(job, pos, photo, status="passed")
        key = f"editor/clip-{pos}.webm"
        files.put(key, str(clip))
        set_final_attempt(shot, add_attempt(shot, 1, "passed", key, requested_s=4))
        execute(
            "update job_shots set cropped_key=:k, edit_status='crop_only' where id=:i",
            k=f"photoshoots/{shoot}/{photo}.jpg",
            i=shot,
        )
    yield job, photos, f"{live_server}/jobs/{job}/edit"
    fake.reset()
    fake_video.reset()


def test_saved_photo_movement_and_restore_survive_reload(page, editor_job):
    job, photos, url = editor_job
    before = shot_rows(job)[5]["final_attempt_id"]
    page.goto(url)
    form = open_shot(page, 2)
    form.get_by_label("Swap the room (photo)").select_option(photos[6])
    expect(tile_change(page, 2)).to_have_text("will be made again")
    expect(form.locator("h2")).to_have_text("Shot 2 · Kitchen")
    expect(page.locator('.ed-grid[data-position="2"] .original-photo')).to_have_attribute(
        "src", re.compile(photos[6])
    )
    open_shot(page, 3).get_by_label("Camera movement").select_option("crane_up")
    expect(tile_change(page, 3)).to_have_text("will be made again")
    form = open_shot(page, 5)
    form.get_by_role("button", name="Remove this room from the video").click()
    expect(tile_change(page, 5)).to_have_text("removed")
    form.get_by_role("button", name="Put this room back").click()
    expect(tile_change(page, 5)).to_have_text("unchanged")

    page.reload()

    expect(tile_change(page, 2)).to_have_text("will be made again")
    expect(tile_change(page, 3)).to_have_text("will be made again")
    expect(open_shot(page, 2).get_by_label("Swap the room (photo)")).to_have_value(photos[6])
    expect(open_shot(page, 3).get_by_label("Camera movement")).to_have_value("crane_up")
    expect(tile_change(page, 5)).to_have_text("unchanged")
    assert shot_rows(job)[5]["final_attempt_id"] == before
    print(
        "AC1: photo swap saved as Kitchen; Crane Up saved; "
        "both cards will be made again after reload"
    )
    print("AC9: shot 5 restored unchanged with its original final attempt")


def test_real_save_failure_stays_inline_and_blocks_export(page, editor_job):
    job, _, url = editor_job
    page.goto(url)
    length = open_shot(page, 1).get_by_label("Length")
    length.fill("0")
    length.blur()
    page.get_by_role("button", name="Re-export video").click()

    expect(page.locator('.field-error[data-for="lengthS"]').first).not_to_be_empty()
    expect(page.locator(".export-note")).to_contain_text("Some changes were not saved")
    assert queue.get_job(job).status == "ready"
    page.reload()
    expect(open_shot(page, 1).get_by_label("Length")).to_have_value("3")


def test_queued_saves_export_once_and_new_video_plays_after_reload(
    page, editor_job, monkeypatch, tmp_path
):
    job, photos, url = editor_job
    requests = []
    page.on("request", lambda request: requests.append(request.method + " " + request.url))
    page.goto(url)
    open_shot(page, 2).get_by_label("Swap the room (photo)").select_option(photos[6])
    expect(tile_change(page, 2)).to_have_text("will be made again")
    open_shot(page, 3).get_by_label("Camera movement").select_option("crane_up")
    expect(tile_change(page, 3)).to_have_text("will be made again")
    form = open_shot(page, 5)
    form.get_by_role("button", name="Remove this room from the video").click()
    expect(tile_change(page, 5)).to_have_text("removed")
    form.get_by_role("button", name="Put this room back").click()
    entered, release = threading.Event(), threading.Event()
    allowed_lengths = fake.FakeProviders.allowed_lengths

    def delayed_limits(self, model):
        entered.set()
        if not release.wait(15):
            raise TimeoutError("Browser did not release the saved edit")
        return allowed_lengths(self, model)

    monkeypatch.setattr(fake.FakeProviders, "allowed_lengths", delayed_limits)
    length = open_shot(page, 1).get_by_label("Length")
    length.fill("2.5")
    length.blur()
    started = time.monotonic()
    try:
        assert entered.wait(5)
        button = page.get_by_role("button", name="Re-export video")
        button.dblclick()
        expect(button).to_be_disabled()
        assert not any(item.startswith("POST ") for item in requests)
    finally:
        release.set()
    expect(page).to_have_url(url.removesuffix("/edit"))
    assert (
        sum(item == f"POST {url.split('/jobs/')[0]}/api/jobs/{job}/export" for item in requests)
        == 1
    )
    assert shot_rows(job)[1]["length_s"] == 2.5
    assert not shot_rows(job)[5]["removed"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(runner.run_next_job).result(timeout=120)
    # Adapt the real assembled version to VP8/Opus supported by the gate browser
    # and FFmpeg build (which lacks libvorbis). No page,
    # API, Jobs or worker response is replaced; the version stays in the test bucket.
    output = tmp_path / "assembled.mp4"
    browser_video = tmp_path / "browser.webm"
    from app.files.keys import video_key

    key = video_key(job, 2)
    files.get(key, str(output))
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(output),
            "-c:v",
            "libvpx",
            "-deadline",
            "realtime",
            "-cpu-used",
            "8",
            "-c:a",
            "libopus",
            str(browser_video),
        ],
        check=True,
    )
    files.put(key, str(browser_video))
    for _ in range(2):
        page.reload()
        expect(page.locator(".player")).to_contain_text("Version 2")
        page.locator(".player video").evaluate("v => { v.muted = true; return v.play(); }")
        page.wait_for_function("document.querySelector('.player video').currentTime > 0.1")
    elapsed = time.monotonic() - started
    assert elapsed <= 600
    print(
        f"AC3: click to version 2 playback and reload playback in {elapsed:.2f}s; "
        "two fake-provider remakes, not real-provider timing"
    )
