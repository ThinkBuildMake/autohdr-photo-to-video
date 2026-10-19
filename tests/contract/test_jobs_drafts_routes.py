import pytest

from app.jobs import store
from app.library.stubs import STUB_SONG_ID
from app.shared.types import PlannedShot
from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS
from tests.support.jobs_rows import (
    add_draft_job,
    add_ready_shoot,
    planned_shot,
    planning_idle,  # noqa: F401
    scripted_planner,  # noqa: F401
)
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = pytest.mark.usefixtures("stub_presets", "planning_idle")


def _job_body(photoshoot_id):
    return {"photoshootId": photoshoot_id, "styleText": "Slow and warm.", "songId": STUB_SONG_ID}


def _ready_draft():
    photoshoot_id, photo_ids = add_ready_shoot(2)
    job_id = add_draft_job(photoshoot_id, STUB_SONG_ID, plan_status="ready")
    shots = [planned_shot(i, pid) for i, pid in enumerate(photo_ids, start=1)]
    store.replace_plan(job_id, [PlannedShot.model_validate(s) for s in shots], None)
    return job_id, shots


def test_create_job(client, scripted_planner):  # noqa: F811
    photoshoot_id, photo_ids = add_ready_shoot(2)
    scripted_planner.queue([planned_shot(i, p) for i, p in enumerate(photo_ids, start=1)])

    response = client.post("/api/jobs", json=_job_body(photoshoot_id))

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["status"] == "draft"
    assert body["job"]["planStatus"] == "planning"


def test_create_job_unknown_photoshoot(client):
    response = client.post("/api/jobs", json=_job_body("nope"))

    assert response.status_code == 404
    assert response.json()["error"] == "photoshoot_not_found"


def test_replan_job(client, scripted_planner):  # noqa: F811
    job_id, shots = _ready_draft()
    scripted_planner.queue(shots)

    response = client.post(f"/api/jobs/{job_id}/plan", json={"styleText": "Faster."})

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["planStatus"] == "planning"


def test_update_job_shots(client):
    job_id, shots = _ready_draft()

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": shots})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert set(body["job"]["shots"][0]) == SHOT_KEYS
