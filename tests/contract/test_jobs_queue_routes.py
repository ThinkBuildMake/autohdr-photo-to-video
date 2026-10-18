from app.jobs.stubs import STUB_JOB_ID
from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS, VIDEO_KEYS


def test_submit_job(client):
    response = client.post(f"/api/jobs/{STUB_JOB_ID}/submit")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["status"] == "queued"


def test_list_jobs(client):
    response = client.get("/api/jobs")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"jobs"}
    assert set(body["jobs"][0]) == {
        "id", "styleName", "photoshootLabel", "purpose", "status", "submittedAt", "elapsedS",
    }  # fmt: skip


def test_get_job(client):
    response = client.get(f"/api/jobs/{STUB_JOB_ID}")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert set(body["job"]["shots"][0]) == SHOT_KEYS
    assert set(body["job"]["video"]) == VIDEO_KEYS


def test_get_video(client):
    response = client.get(f"/api/jobs/{STUB_JOB_ID}/video")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"url", "downloadUrl", "durationS"}


def test_get_video_of_unknown_job(client):
    response = client.get("/api/jobs/nope/video")

    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"
