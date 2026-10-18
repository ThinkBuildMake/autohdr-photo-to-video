from app.jobs.stubs import STUB_JOB_ID
from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS


def test_restart_job(client):
    response = client.post(f"/api/jobs/{STUB_JOB_ID}/restart")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS


def test_edit_shot(client):
    response = client.patch(f"/api/jobs/{STUB_JOB_ID}/shots/0", json={"lengthS": 2.0})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"shot", "exportPlan"}
    assert set(body["shot"]) == SHOT_KEYS
    assert set(body["exportPlan"]) == {"newClips", "recutOnly", "removed"}
    assert body["shot"]["lengthS"] == 2.0


def test_edit_unknown_shot(client):
    response = client.patch(f"/api/jobs/{STUB_JOB_ID}/shots/99", json={"lengthS": 2.0})

    assert response.status_code == 404
    assert response.json()["error"] == "shot_not_found"


def test_export_job(client):
    response = client.post(f"/api/jobs/{STUB_JOB_ID}/export")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS


def test_redo_shot(client):
    response = client.post(f"/api/jobs/{STUB_JOB_ID}/shots/1/redo")

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
