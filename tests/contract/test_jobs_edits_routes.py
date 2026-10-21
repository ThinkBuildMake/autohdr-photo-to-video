from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS
from tests.support.bucket import bucket  # noqa: F401
from tests.support.queue_rows import (
    add_attempt,
    add_job,
    add_shoot,
    add_shot,
    add_song,
    set_final_attempt,
)


def _finished_job(status="ready", stop_reason=None):
    shoot_id, photos = add_shoot()
    job_id = add_job(
        shoot_id,
        add_song(),
        status=status,
        stop_reason=stop_reason,
        submitted_at="2026-10-19T08:00:00.000Z",
        finished_at="2026-10-19T08:05:00.000Z",
    )
    shot_id = add_shot(job_id, 1, photos[0], status="passed")
    clip = f"jobs/{job_id}/shots/1/r0/a1.mp4"
    set_final_attempt(shot_id, add_attempt(shot_id, 1, "passed", clip, requested_s=4.0))
    add_shot(job_id, 2, photos[1], status="failed", failure_reason="provider_error")
    return job_id


def test_restart_job(bucket, client):  # noqa: F811
    job_id = _finished_job(status="stopped", stop_reason="out_of_credit")

    response = client.post(f"/api/jobs/{job_id}/restart")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS


def test_edit_shot(bucket, client):  # noqa: F811
    job_id = _finished_job()

    response = client.patch(f"/api/jobs/{job_id}/shots/1", json={"lengthS": 2.0})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"shot", "exportPlan", "warning"}
    assert body["warning"] is None
    assert set(body["shot"]) == SHOT_KEYS
    assert set(body["exportPlan"]) == {"newClips", "recutOnly", "removed"}
    assert body["shot"]["lengthS"] == 2.0


def test_edit_unknown_shot(bucket, client):  # noqa: F811
    job_id = _finished_job()

    response = client.patch(f"/api/jobs/{job_id}/shots/99", json={"lengthS": 2.0})

    assert response.status_code == 404
    assert response.json()["error"] == "shot_not_found"


def test_export_job(bucket, client):  # noqa: F811
    job_id = _finished_job()
    client.patch(f"/api/jobs/{job_id}/shots/1", json={"lengthS": 2.0})

    response = client.post(f"/api/jobs/{job_id}/export")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS


def test_redo_shot(bucket, client):  # noqa: F811
    job_id = _finished_job()

    response = client.post(f"/api/jobs/{job_id}/shots/1/redo")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
