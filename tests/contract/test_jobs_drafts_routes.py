import pytest

from app.jobs.stubs import STUB_JOB_ID
from app.library.stubs import STUB_SONG_ID
from app.photoshoots.stubs import STUB_PHOTO_IDS, STUB_PHOTOSHOOT_ID
from tests.contract._jobs_common import JOB_KEYS, SHOT_KEYS
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = pytest.mark.usefixtures("stub_presets")


def _job_body():
    return {
        "photoshootId": STUB_PHOTOSHOOT_ID,
        "styleText": "Slow and warm.",
        "songId": STUB_SONG_ID,
    }


def _planned_shot(position):
    return {
        "position": position,
        "room": "living",
        "photoId": STUB_PHOTO_IDS[position],
        "photoEditPrompts": [],
        "movementName": "dolly_in",
        "movementPrompt": "Slow dolly in.",
        "speed": "slow",
        "model": "google/veo-3.1",
        "lengthS": 3.0,
        "transition": "cut",
        "transitionS": 0.0,
        "planNote": "",
    }


def test_create_job(client):
    response = client.post("/api/jobs", json=_job_body())

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["status"] == "draft"
    assert body["job"]["planStatus"] == "planning"


def test_create_job_unknown_photoshoot(client):
    response = client.post("/api/jobs", json={**_job_body(), "photoshootId": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "photoshoot_not_found"


def test_replan_job(client):
    response = client.post(f"/api/jobs/{STUB_JOB_ID}/plan", json={"styleText": "Faster."})

    body = response.json()
    assert response.status_code == 202
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert body["job"]["planStatus"] == "planning"


def test_update_job_shots(client):
    response = client.put(
        f"/api/jobs/{STUB_JOB_ID}/shots", json={"shots": [_planned_shot(0), _planned_shot(1)]}
    )

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"job"}
    assert set(body["job"]) == JOB_KEYS
    assert set(body["job"]["shots"][0]) == SHOT_KEYS
