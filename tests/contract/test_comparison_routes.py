import pytest

from app.jobs.stubs import STUB_JOB_ID
from app.library.stubs import CRISP_MODERN_ID, GOLDEN_HOUR_ID
from tests.support.library_rows import stub_presets  # noqa: F401

pytestmark = pytest.mark.usefixtures("stub_presets")

STYLE_KEYS = {
    "id", "name", "authorName", "styleText", "song", "songOffsetS", "fps",
    "demoPhotoshootId", "referenceJobId",
}  # fmt: skip
SUMMARY_KEYS = {"shotCount", "totalS", "medianShotS", "movements", "transitions"}


def test_set_reference(client):
    response = client.post(f"/api/styles/{CRISP_MODERN_ID}/reference", json={"jobId": STUB_JOB_ID})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"style"}
    assert set(body["style"]) == STYLE_KEYS


def test_set_reference_unknown_job(client):
    response = client.post(f"/api/styles/{CRISP_MODERN_ID}/reference", json={"jobId": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"


def test_get_reproduction(client):
    response = client.get(f"/api/styles/{GOLDEN_HOUR_ID}/reproductions/{STUB_JOB_ID}")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {
        "reference", "reproduction", "song", "sameText", "summary", "shots", "maxCutErrorS",
    }  # fmt: skip
    assert set(body["reference"]) == {"jobId", "videoUrl", "photoshootLabel"}
    assert set(body["reproduction"]) == {"jobId", "videoUrl", "photoshootLabel"}
    assert set(body["song"]) == {"sameSong", "credit"}
    assert set(body["summary"]) == {"reference", "reproduction"}
    assert set(body["summary"]["reference"]) == SUMMARY_KEYS
    assert set(body["shots"][0]) == {
        "position", "movementName", "transition", "reference", "reproduction", "flagged",
    }  # fmt: skip
    assert set(body["shots"][0]["reference"]) == {"lengthS", "cutErrorS"}


def test_get_reproduction_without_reference(client):
    response = client.get(f"/api/styles/{CRISP_MODERN_ID}/reproductions/{STUB_JOB_ID}")

    assert response.status_code == 409
    assert response.json()["error"] == "no_reference"
