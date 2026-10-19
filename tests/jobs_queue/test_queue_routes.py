from urllib.parse import parse_qs, urlparse

from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shot,
    job_row,
    set_final_attempt,
)


def _draft(shoot, song, photos=2, **kwargs):
    shoot_id, photo_ids = shoot
    job_id = add_job(shoot_id, song, **kwargs)
    for position in range(photos):
        add_shot(job_id, position, photo_ids[position])
    return job_id


def test_submit_queues_a_ready_draft(client, song, shoot):
    job_id = _draft(shoot, song)

    response = client.post(f"/api/jobs/{job_id}/submit")

    assert response.status_code == 202
    job = response.json()["job"]
    assert job["status"] == "queued"
    assert job["submittedAt"] is not None
    row = job_row(job_id)
    assert row["status"] == "queued"
    assert row["first_submitted_at"] is not None
    assert row["first_submitted_at"] == row["submitted_at"]


def test_second_job_waits_behind_the_running_one(client, song, shoot):
    shoot_id, _ = shoot
    running = add_job(shoot_id, song, status="running", started_at="2026-10-19T08:00:00.000Z")
    waiting = _draft(shoot, song)

    response = client.post(f"/api/jobs/{waiting}/submit")

    assert response.status_code == 202
    assert response.json()["job"]["waitingBehind"] == running
    job = client.get(f"/api/jobs/{waiting}").json()["job"]
    assert job["status"] == "queued"
    assert job["waitingBehind"] == running


def test_draft_with_every_shot_skipped_is_refused(client, song, shoot):
    shoot_id, _ = shoot
    job_id = add_job(shoot_id, song)
    add_shot(job_id, 0, None)
    add_shot(job_id, 1, None)

    response = client.post(f"/api/jobs/{job_id}/submit")

    assert response.status_code == 409
    assert response.json()["error"] == "no_shots_to_make"
    row = job_row(job_id)
    assert row["status"] == "draft"
    assert row["first_submitted_at"] is None


def test_submit_errors(client, song, shoot):
    shoot_id, photos = shoot
    queued = add_job(shoot_id, song, status="queued", submitted_at="2026-10-19T08:00:00.000Z")
    planning = _draft(shoot, song, plan_status="planning")

    unknown = client.post("/api/jobs/nope/submit")
    not_draft = client.post(f"/api/jobs/{queued}/submit")
    not_ready = client.post(f"/api/jobs/{planning}/submit")

    assert (unknown.status_code, unknown.json()["error"]) == (404, "job_not_found")
    assert (not_draft.status_code, not_draft.json()["error"]) == (409, "not_draft")
    assert (not_ready.status_code, not_ready.json()["error"]) == (409, "plan_not_ready")
    assert job_row(planning)["status"] == "draft"


def test_submit_marks_photoless_shots_skipped(client, song, shoot):
    shoot_id, photos = shoot
    job_id = add_job(shoot_id, song)
    add_shot(job_id, 0, photos[0])
    add_shot(job_id, 1, None)

    shots = client.post(f"/api/jobs/{job_id}/submit").json()["job"]["shots"]

    assert [s["status"] for s in shots] == ["pending", "skipped"]
    assert shots[1]["failureReason"] == "no_photo"


def test_getjob_shows_attempt_2_clip(bucket, client, song, shoot):
    shoot_id, photos = shoot
    job_id = add_job(shoot_id, song, status="ready")
    shot_id = add_shot(job_id, 0, photos[0], status="passed")
    add_attempt(shot_id, 1, "flagged", clip_key=f"jobs/{job_id}/shots/1/r0/a1.mp4")
    second = add_attempt(shot_id, 2, "passed", clip_key=f"jobs/{job_id}/shots/1/r0/a2.mp4")
    set_final_attempt(shot_id, second)

    clip_url = client.get(f"/api/jobs/{job_id}").json()["job"]["shots"][0]["clipUrl"]

    assert "/a2.mp4" in clip_url
    assert "/a1.mp4" not in clip_url


def test_get_jobs_newest_first(client, song, shoot):
    shoot_id, _ = shoot
    # inserted and submitted out of created order, so only created_at ordering passes
    newest = add_job(
        shoot_id, song, status="ready", created_at="2026-10-19T11:00:00.000Z",
        submitted_at="2026-10-19T11:01:00.000Z", finished_at="2026-10-19T11:06:00.000Z",
    )  # fmt: skip
    oldest = add_job(
        shoot_id, song, status="ready", created_at="2026-10-19T09:00:00.000Z",
        submitted_at="2026-10-19T12:01:00.000Z", finished_at="2026-10-19T12:06:00.000Z",
    )  # fmt: skip
    middle = add_job(
        shoot_id, song, status="ready", created_at="2026-10-19T10:00:00.000Z",
        submitted_at="2026-10-19T08:01:00.000Z", finished_at="2026-10-19T08:06:00.000Z",
    )  # fmt: skip

    jobs = client.get("/api/jobs").json()["jobs"]

    assert [j["id"] for j in jobs] == [newest, middle, oldest]
    assert all(j["status"] == "ready" for j in jobs)
    assert all(isinstance(j["elapsedS"], float) for j in jobs)


def test_ready_job_video_links(bucket, client, song, shoot):
    shoot_id, _ = shoot
    job_id = add_job(
        shoot_id, song, status="ready", video_key="jobs/J/video-v1.mp4", video_duration_s=42.5
    )

    response = client.get(f"/api/jobs/{job_id}/video")

    assert response.status_code == 200
    body = response.json()
    assert body["durationS"] == 42.5
    play = parse_qs(urlparse(body["url"]).query)
    download = parse_qs(urlparse(body["downloadUrl"]).query)
    assert play["X-Amz-Expires"] == ["3600"]
    assert "response-content-disposition" not in play
    assert download["response-content-disposition"][0].startswith("attachment")


def test_queued_job_has_no_video(client, song, shoot):
    shoot_id, _ = shoot
    job_id = add_job(shoot_id, song, status="queued", submitted_at="2026-10-19T08:00:00.000Z")

    no_video = client.get(f"/api/jobs/{job_id}/video")
    unknown = client.get("/api/jobs/nope/video")

    assert no_video.status_code == 409
    assert no_video.json()["error"] == "no_video"
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "job_not_found"


def test_submit_never_starts_a_second_running_job(client, song, shoot):
    shoot_id, _ = shoot
    running = add_job(shoot_id, song, status="running", started_at="2026-10-19T08:00:00.000Z")
    second = _draft(shoot, song)
    third = _draft(shoot, song)

    for job_id in (second, third):
        assert client.post(f"/api/jobs/{job_id}/submit").status_code == 202

    assert job_row(running)["status"] == "running"
    assert job_row(running)["started_at"] == "2026-10-19T08:00:00.000Z"
    assert job_row(second)["status"] == "queued"
    assert job_row(third)["status"] == "queued"
    for job_id in (second, third):
        assert client.get(f"/api/jobs/{job_id}").json()["job"]["waitingBehind"] == running
