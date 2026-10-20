import pytest

from app.jobs import reading
from app.jobs.errors import JobNotFound
from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shot,
    set_final_attempt,
)

NOW = "2026-10-19T12:00:00.000Z"


def test_flagged_attempt_clip_never_reaches_getjob(bucket, song, shoot):
    shoot_id, photos = shoot
    job_id = add_job(shoot_id, song, status="ready", video_key=None)
    shot_id = add_shot(job_id, 0, photos[0], status="passed")
    add_attempt(shot_id, 1, "flagged", clip_key=f"jobs/{job_id}/shots/1/r0/a1.mp4")
    second = add_attempt(shot_id, 2, "passed", clip_key=f"jobs/{job_id}/shots/1/r0/a2.mp4")
    set_final_attempt(shot_id, second)
    flagged_shot = add_shot(job_id, 1, photos[1], status="passed")
    only = add_attempt(flagged_shot, 1, "flagged", clip_key=f"jobs/{job_id}/shots/2/r0/a1.mp4")
    set_final_attempt(flagged_shot, only)

    shots = reading.load_job(job_id).shots

    assert "/a2.mp4" in shots[0].clip_url
    assert "/a1.mp4" not in shots[0].clip_url
    assert shots[0].attempts == 2
    assert shots[1].clip_url is None


def test_attempts_count_only_the_current_round(bucket, song, shoot):
    shoot_id, photos = shoot
    job_id = add_job(shoot_id, song, status="ready")
    shot_id = add_shot(job_id, 0, photos[0], status="passed", round=1)
    add_attempt(shot_id, 1, "flagged", round=0)
    add_attempt(shot_id, 2, "flagged", round=0)
    final = add_attempt(shot_id, 1, "passed", clip_key="jobs/J/shots/1/r1/a1.mp4", round=1)
    set_final_attempt(shot_id, final)

    assert reading.load_job(job_id).shots[0].attempts == 1


def test_list_jobs_newest_first_with_status_and_elapsed(song, shoot, monkeypatch):
    monkeypatch.setattr(reading, "now_utc", lambda: NOW)
    shoot_id, _ = shoot
    # inserted and submitted out of created order, so only created_at ordering passes
    newest = add_job(
        shoot_id,
        song,
        status="queued",
        created_at="2026-10-19T11:00:00.000Z",
        submitted_at="2026-10-19T08:30:00.000Z",
    )
    oldest = add_job(
        shoot_id,
        song,
        status="ready",
        created_at="2026-10-19T09:00:00.000Z",
        submitted_at="2026-10-19T11:59:00.000Z",
        finished_at="2026-10-19T12:04:00.000Z",
    )
    middle = add_job(
        shoot_id,
        song,
        status="running",
        created_at="2026-10-19T10:00:00.000Z",
        submitted_at="2026-10-19T11:50:00.000Z",
    )

    items = reading.list_jobs()

    assert [item.id for item in items] == [newest, middle, oldest]
    assert [item.status for item in items] == ["queued", "running", "ready"]
    assert items[1].elapsed_s == 600.0
    assert items[2].elapsed_s == 300.0
    assert items[0].photoshoot_label == "12 Oak Street"
    assert items[0].style_name == "Custom style"


def test_failed_and_skipped_shots_are_listed_with_reason(bucket, song, shoot):
    shoot_id, photos = shoot
    job_id = add_job(shoot_id, song, status="ready_with_failures")
    passed = add_shot(job_id, 0, photos[0], status="passed")
    clip = add_attempt(passed, 1, "passed", clip_key="jobs/J/shots/1/r0/a1.mp4")
    set_final_attempt(passed, clip)
    add_shot(
        job_id,
        1,
        photos[1],
        status="failed",
        failure_reason="flagged_every_attempt",
        status_detail="Attempt 4 of 4: flagged",
    )
    add_shot(job_id, 2, None, status="skipped", failure_reason="no_photo")

    shots = reading.load_job(job_id).shots

    assert [shot.position for shot in shots] == [0, 1, 2]
    assert shots[0].clip_url is not None
    assert shots[1].failure_reason == "flagged_every_attempt"
    assert shots[1].status_detail == "Attempt 4 of 4: flagged"
    assert shots[1].clip_url is None
    assert shots[2].failure_reason == "no_photo"
    assert shots[2].photo_id is None


def test_queued_job_waits_behind_the_running_one(song, shoot):
    shoot_id, _ = shoot
    queued_alone = add_job(shoot_id, song, status="queued", submitted_at=NOW)
    assert reading.load_job(queued_alone).waiting_behind is None

    running = add_job(shoot_id, song, status="running", submitted_at=NOW)
    queued = add_job(shoot_id, song, status="queued", submitted_at=NOW)

    assert reading.load_job(queued).waiting_behind == running
    assert reading.load_job(running).waiting_behind is None


@pytest.mark.parametrize(
    ("status", "submitted", "finished", "expected"),
    [
        ("draft", None, None, 0.0),
        ("queued", "2026-10-19T11:58:00.000Z", None, 120.0),
        ("running", "2026-10-19T11:50:00.000Z", None, 600.0),
        ("ready", "2026-10-19T09:00:00.000Z", "2026-10-19T09:05:00.000Z", 300.0),
        ("stopped", "2026-10-19T09:00:00.000Z", None, 0.0),
        ("running", "2026-10-19T12:30:00.000Z", None, 0.0),
    ],
)
def test_elapsed_rules(status, submitted, finished, expected):
    assert reading.elapsed_s(status, submitted, finished, NOW) == expected


def test_ready_job_carries_the_video_and_credit(bucket, song, shoot):
    shoot_id, _ = shoot
    job_id = add_job(
        shoot_id,
        song,
        status="ready",
        video_key="jobs/J/video-v1.mp4",
        video_duration_s=42.5,
        video_width=1920,
        video_height=1080,
        video_version=3,
    )

    job = reading.load_job(job_id)

    assert "video-v1.mp4" in job.video.url
    assert (job.video.duration_s, job.video.width, job.video.height) == (42.5, 1920, 1080)
    assert job.video.version == 3
    assert job.song_credit.startswith("Track A, Artist A")


def test_unknown_job_is_job_not_found(song):
    with pytest.raises(JobNotFound):
        reading.load_job("nope")
