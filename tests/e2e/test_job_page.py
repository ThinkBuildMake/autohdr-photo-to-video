import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import expect

from app.errors import AppError
from app.jobs import edits
from app.shared.enums import FailureReason, JobStatus, ShotStatus, StopReason
from app.shared.types import JobVideo
from tests.support.job_screens import JOB_A, JOB_B, job, shot, stub_jobs  # noqa: F401

pytestmark = pytest.mark.e2e

CHECK_NOTES = "Looked AI-generated after 4 attempts: the cabinet doors warp."
SOURCE_URL = "https://freemusicarchive.org/music/Artist_A/Track_A"


def running_job(**changes):
    return job(
        status=JobStatus.running,
        finished_at=None,
        video=None,
        shots=[
            shot(1, status=ShotStatus.generating, status_detail="Attempt 1 of 4"),
            shot(
                2,
                status=ShotStatus.generating,
                attempts=2,
                status_detail="Attempt 2 of 4: flagged, a person appears",
            ),
            shot(3, status=ShotStatus.passed),
        ],
        **changes,
    )


def test_running_job_shows_each_shot_detail(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(running_job())

    page.goto(f"{live_server}/jobs/{JOB_A}")

    card = page.locator("#shot-2")
    assert "Attempt 2 of 4: flagged, a person appears" in card.inner_text()
    assert card.locator(".chip").inner_text() == "Trying again"


def test_running_job_updates_itself(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(running_job())
    page.goto(f"{live_server}/jobs/{JOB_A}")
    page.evaluate("window.notReloaded = true")
    first = page.locator("#shot-1 .chip")
    assert first.inner_text() == "Making the clip"

    current = stub_jobs.jobs[JOB_A]
    passed = shot(1, status=ShotStatus.passed, status_detail="Passed the check.")
    shots = [passed, *current.shots[1:]]
    stub_jobs.add(current.model_copy(update={"shots": shots}))

    page.wait_for_function(
        "document.querySelector('#shot-1 .chip').innerText === 'Passed'", timeout=5500
    )
    assert page.evaluate("window.notReloaded") is True


def test_polling_stops_once_the_job_finishes(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(running_job())
    page.goto(f"{live_server}/jobs/{JOB_A}")
    stub_jobs.add(job(status=JobStatus.ready))
    expect(page.get_by_text("Your video is ready")).to_be_visible(timeout=8000)

    polls = []
    page.on("request", lambda request: polls.append(request.url))
    page.wait_for_timeout(6000)

    assert [url for url in polls if url.endswith(f"/jobs/{JOB_A}")] == []


def test_a_failed_poll_says_so_and_keeps_trying(page, live_server, stub_jobs):  # noqa: F811
    running = running_job()
    stub_jobs.add(running)
    page.goto(f"{live_server}/jobs/{JOB_A}")

    del stub_jobs.jobs[JOB_A]
    expect(page.get_by_role("alert")).to_contain_text("Could not refresh", timeout=8000)

    stub_jobs.add(running)
    expect(page.locator(".action-error")).to_be_empty(timeout=8000)


def test_queued_job_says_what_it_waits_for(page, live_server, stub_jobs):  # noqa: F811
    running_id = "a1b2c3d4-0000-4000-8000-00000000000a"
    stub_jobs.add(
        job(
            JOB_B,
            status=JobStatus.queued,
            waiting_behind=running_id,
            waiting_behind_label="Condo",
            finished_at=None,
            video=None,
        )
    )

    page.goto(f"{live_server}/jobs/{JOB_B}")

    assert page.get_by_text("Waiting: another video is being made").is_visible()
    assert page.get_by_text("Waiting for job a1b2c3d4 to finish.").is_visible()
    assert (
        "Yours starts as soon as the Condo video finishes" in page.locator(".b-warn").inner_text()
    )
    assert "Estimated wait: usually under 10 minutes" in page.locator(".b-warn").inner_text()
    assert page.get_by_role("link", name="a1b2c3d4").get_attribute("href") == f"/jobs/{running_id}"


def test_submit_time_shows_in_local_time(
    browser,
    browser_context_args,
    live_server,
    stub_jobs,  # noqa: F811
):
    stub_jobs.add(running_job(submitted_at="2026-10-19T17:00:00Z"))
    context = browser.new_context(**browser_context_args, timezone_id="America/Phoenix")  # UTC−7
    page = context.new_page()

    page.goto(f"{live_server}/jobs/{JOB_A}")

    meta = page.locator(".meta").inner_text()
    context.close()
    assert "10:00" in meta
    assert "17:00" not in meta


def test_stopped_job_names_the_reason(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(job(status=JobStatus.stopped, stop_reason=StopReason.out_of_credit, video=None))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    banner = page.locator(".banner.b-err")
    assert "the video service account is out of credit" in banner.inner_text()
    assert "Shots 1, 2, 3 and 4 are finished and kept." in banner.inner_text()
    assert banner.get_by_role("button", name="Start again").is_visible()


def test_header_names_the_property_and_photos(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(job(photoshoot_label="4-bed house", photo_count=28))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    assert page.locator(".meta").inner_text().startswith("4-bed house, 28 photos · Style:")
    assert "Took 5 min. Watch it before you send it to the agent." in page.inner_text("#job")


def ready_with_failures(*failed_shots):
    by_position = {s.position: s for s in failed_shots}
    shots = [by_position.get(n, shot(n)) for n in (1, 2, 3, 4)]
    return job(status=JobStatus.ready_with_failures, shots=shots)


def test_failed_shot_is_marked_beside_the_player(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(
        ready_with_failures(
            shot(
                3,
                status=ShotStatus.failed,
                failure_reason=FailureReason.flagged_every_attempt,
                status_detail=CHECK_NOTES,
                attempts=4,
            )
        )
    )

    page.goto(f"{live_server}/jobs/{JOB_A}")

    player = page.locator(".player")
    assert player.locator("video").count() == 1
    failures = page.locator("#job > .failures").inner_text()
    assert page.locator(".failures").bounding_box()["y"] < player.bounding_box()["y"]
    assert "Shot 3" in failures
    assert "Failed the check on every attempt" in failures
    assert CHECK_NOTES in failures
    assert page.locator("#shot-3 .chip").inner_text() == "Failed"
    assert page.locator("#shot-3 .attempts").inner_text() == "Attempts: 4 of 4 this round"
    assert CHECK_NOTES in page.locator("#shot-3").inner_text()


def test_every_failed_shot_is_listed_with_its_reason(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(
        ready_with_failures(
            shot(2, status=ShotStatus.failed, failure_reason=FailureReason.provider_error),
            shot(3, status=ShotStatus.failed, failure_reason=FailureReason.refused),
            shot(4, status=ShotStatus.skipped, failure_reason=FailureReason.no_photo),
        )
    )

    page.goto(f"{live_server}/jobs/{JOB_A}")

    items = page.locator("#job > .failures li").all_inner_texts()
    assert len(items) == 3
    assert "Shot 2" in items[0] and "The video service returned an error" in items[0]
    assert "Shot 3" in items[1] and "The video service refused this shot" in items[1]
    assert "Shot 4" in items[2] and "No photo of this room" in items[2]


def test_departures_are_shown_on_the_shot(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(
        job(
            shots=[
                shot(1, edit_status="crop_only", edit_note="The edit added a second window."),
                shot(2),
                shot(3),
                shot(4, model="bytedance/seedance-2.0", used_fallback=True),
            ]
        )
    )

    page.goto(f"{live_server}/jobs/{JOB_A}")

    first = page.locator("#shot-1").inner_text()
    assert "crop only" in first and "The edit added a second window." in first
    fourth = page.locator("#shot-4").inner_text()
    assert "fallback model" in fourth and "bytedance/seedance-2.0" in fourth
    assert "fallback model" not in page.locator("#shot-2").inner_text()
    assert "crop only" not in page.locator("#shot-2").inner_text()


DOWNLOAD_NAME = f"video-{JOB_A[:8]}-v2.mp4"


@pytest.fixture
def webm(tmp_path):
    """A 2 s VP8 clip: the test browser has no H.264 decoder."""
    path = tmp_path / "video.webm"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=s=320x180:r=24:d=2", "-c:v", "libvpx", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


@pytest.fixture
def media_server(webm):
    """Stands in for the bucket: plays the clip, or saves it when the link asks for a download."""

    class Media(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/webm")
            self.send_header("Content-Length", str(len(webm)))
            if self.path.endswith("?download"):
                self.send_header("Content-Disposition", f'attachment; filename="{DOWNLOAD_NAME}"')
            self.end_headers()
            self.wfile.write(webm)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Media)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_video_plays_and_downloads(page, live_server, stub_jobs, media_server, webm):  # noqa: F811
    url = f"{media_server}/video-v2.webm"
    video = JobVideo(url=url, duration_s=2.0, width=320, height=180, version=2)
    stub_jobs.add(job(video=video))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    played = page.locator(".player video").evaluate(
        "v => { v.muted = true; return v.play()"
        ".then(() => new Promise(done => setTimeout(done, 500))).then(() => v.currentTime) }"
    )
    assert played > 0
    assert "Version 2" in page.locator(".player").inner_text()
    with page.expect_download() as info:
        page.get_by_role("link", name="Download video").click()
    download = info.value
    assert download.suggested_filename == DOWNLOAD_NAME
    assert open(download.path(), "rb").read() == webm


def test_song_is_credited(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(job(song_credit=f"Track A, Artist A, CC BY-NC, {SOURCE_URL}"))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    credit = page.locator(".player .credit")
    text = credit.inner_text()
    assert "Track A" in text and "Artist A" in text and "BY-NC" in text
    assert "demo use only" in text
    assert credit.get_by_role("link").get_attribute("href") == SOURCE_URL


@pytest.fixture
def calls(monkeypatch, stub_jobs):  # noqa: F811
    """Records restartJob and redoShot; set `refuse` to answer with an error instead."""
    seen = {"restart": [], "redo": [], "refuse": None, "delay": 0}

    def answer(job_id):
        time.sleep(seen["delay"])
        if seen["refuse"]:
            raise seen["refuse"]
        return stub_jobs.jobs[job_id]

    def restart_job(job_id):
        seen["restart"].append(job_id)
        return answer(job_id)

    def redo_shot(job_id, position):
        seen["redo"].append((job_id, position))
        return answer(job_id)

    monkeypatch.setattr(edits, "restart_job", restart_job)
    monkeypatch.setattr(edits, "redo_shot", redo_shot)
    return seen


def test_start_again_calls_restart(page, live_server, stub_jobs, calls):  # noqa: F811
    stub_jobs.add(job(status=JobStatus.stopped, stop_reason=StopReason.out_of_credit, video=None))
    page.goto(f"{live_server}/jobs/{JOB_A}")

    with page.expect_response(f"**/api/jobs/{JOB_A}/restart") as response:
        page.get_by_role("button", name="Start again").click()

    assert response.value.status == 202
    assert calls["restart"] == [JOB_A]


def test_redo_calls_redo_for_that_shot(page, live_server, stub_jobs, calls):  # noqa: F811
    stub_jobs.add(job())
    page.goto(f"{live_server}/jobs/{JOB_A}")

    with page.expect_response(f"**/api/jobs/{JOB_A}/shots/2/redo") as response:
        page.locator("#shot-2").get_by_role("button", name="Redo this shot").click()

    assert response.value.status == 202
    assert calls["redo"] == [(JOB_A, 2)]


def test_a_refused_redo_shows_its_message(page, live_server, stub_jobs, calls):  # noqa: F811
    stub_jobs.add(job())
    calls["refuse"] = AppError(409, "job_busy", "This job is being made: wait for it to finish.")
    page.goto(f"{live_server}/jobs/{JOB_A}")

    page.locator("#shot-2").get_by_role("button", name="Redo this shot").click()

    expect(page.get_by_role("alert")).to_have_text("This job is being made: wait for it to finish.")


def test_a_source_that_is_not_a_web_address_is_not_linked(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(job(song_credit="Track A, Artist A, CC BY-NC, javascript:alert(1)"))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    credit = page.locator(".player .credit")
    assert "Track A" in credit.inner_text()
    assert credit.locator("a").count() == 0


def test_a_job_made_again_hides_redo_and_the_failures(page, live_server, stub_jobs):  # noqa: F811
    failed = shot(3, status=ShotStatus.failed, failure_reason=FailureReason.flagged_every_attempt)
    stub_jobs.add(job(status=JobStatus.running, shots=[shot(1), shot(2), failed]))

    page.goto(f"{live_server}/jobs/{JOB_A}")

    assert page.locator(".player video").count() == 1
    assert page.get_by_role("button", name="Redo this shot").count() == 0
    assert page.locator(".failures").count() == 0


@pytest.mark.parametrize(
    ("state", "button", "kind"),
    [("stopped", "Start again", "restart"), ("ready", "Redo this shot", "redo")],
)
def test_a_double_click_sends_one_request(page, live_server, stub_jobs, calls, state, button, kind):  # noqa: F811
    if state == "stopped":
        stopped = job(status=JobStatus.stopped, stop_reason=StopReason.out_of_credit, video=None)
        stub_jobs.add(stopped)
    else:
        stub_jobs.add(job())
    calls["refuse"] = AppError(409, "job_busy", "This job is being made.")
    calls["delay"] = 0.5
    page.goto(f"{live_server}/jobs/{JOB_A}")

    page.get_by_role("button", name=button).first.dblclick()

    expect(page.get_by_role("alert")).to_have_text("This job is being made.")
    page.wait_for_timeout(1000)
    assert len(calls[kind]) == 1


def test_a_poll_with_the_server_down_says_so(page, live_server, stub_jobs):  # noqa: F811
    stub_jobs.add(running_job())
    page.goto(f"{live_server}/jobs/{JOB_A}")

    page.route(f"**/jobs/{JOB_A}", lambda route: route.abort("connectionrefused"))

    expect(page.locator(".action-error")).to_contain_text("Could not refresh", timeout=8000)
