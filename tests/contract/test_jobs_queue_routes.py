from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS, VIDEO_KEYS
from tests.support.bucket import bucket  # noqa: F401, F811
from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shoot,
    add_shot,
    add_song,
    set_final_attempt,
)


def _ready_job_with_video():
    song = add_song()
    shoot_id, photos = add_shoot()
    job_id = add_job(
        shoot_id,
        song,
        status="ready",
        submitted_at="2026-10-19T08:00:00.000Z",
        finished_at="2026-10-19T08:05:00.000Z",
        video_key="jobs/J/video-v1.mp4",
        video_duration_s=42.5,
        video_width=1920,
        video_height=1080,
    )
    shot_id = add_shot(job_id, 0, photos[0], status="passed")
    attempt = add_attempt(shot_id, 1, "passed", clip_key=f"jobs/{job_id}/shots/1/r0/a1.mp4")
    set_final_attempt(shot_id, attempt)
    return job_id


def test_submit_job(client):
    song = add_song()
    shoot_id, photos = add_shoot()
    job_id = add_job(shoot_id, song)
    add_shot(job_id, 0, photos[0])

    response = client.post(f"/api/jobs/{job_id}/submit")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["status"] == "queued"


def test_list_jobs(bucket, client):  # noqa: F811
    _ready_job_with_video()

    response = client.get("/api/jobs")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"jobs"}
    assert set(body["jobs"][0]) == {
        "id", "styleName", "photoshootLabel", "purpose", "status", "submittedAt", "elapsedS",
    }  # fmt: skip


def test_get_job(bucket, client):  # noqa: F811
    job_id = _ready_job_with_video()

    response = client.get(f"/api/jobs/{job_id}")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert set(body["job"]["shots"][0]) == SHOT_KEYS
    assert set(body["job"]["video"]) == VIDEO_KEYS


def test_get_video(bucket, client):  # noqa: F811
    job_id = _ready_job_with_video()

    response = client.get(f"/api/jobs/{job_id}/video")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"url", "downloadUrl", "durationS"}


def test_get_video_of_unknown_job(client):
    response = client.get("/api/jobs/nope/video")

    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"
