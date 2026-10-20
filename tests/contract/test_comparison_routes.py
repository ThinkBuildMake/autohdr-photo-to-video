import pytest

from app.library import service as library
from app.library.stubs import CRISP_MODERN_ID, GOLDEN_HOUR_ID, STUB_SONG_ID, STUB_STYLES
from tests.support.comparison_rows import add_cut_check, add_job, add_shot, add_shots
from tests.support.library_rows import add_song, stub_presets  # noqa: F401

pytestmark = pytest.mark.usefixtures("stub_presets")

GOLDEN_TEXT, CRISP_TEXT = (style.style_text for style in STUB_STYLES)
SUMMARY_KEYS = {"shotCount", "totalS", "medianShotS", "movements", "transitions"}


def _reference_of(client, style_id):
    return client.get(f"/api/styles/{style_id}").json()["style"]["referenceJobId"]


def _golden_job(label="12 Oak Street", **kwargs):
    return add_job(
        STUB_SONG_ID, style_id=GOLDEN_HOUR_ID, style_text=GOLDEN_TEXT, label=label, **kwargs
    )


def _with_reference(**kwargs):
    reference = _golden_job(**kwargs)
    library.set_reference_job(GOLDEN_HOUR_ID, reference)
    return reference


def _compare(client, job_id, style_id=GOLDEN_HOUR_ID):
    return client.get(f"/api/styles/{style_id}/reproductions/{job_id}")


def test_set_reference(client):
    job_id = add_job(STUB_SONG_ID, style_id=GOLDEN_HOUR_ID, style_text=GOLDEN_TEXT)

    response = client.post(f"/api/styles/{GOLDEN_HOUR_ID}/reference", json={"jobId": job_id})

    assert response.status_code == 200
    assert response.json()["style"]["referenceJobId"] == job_id
    assert _reference_of(client, GOLDEN_HOUR_ID) == job_id


@pytest.mark.parametrize(
    "status, style_text",
    [("running", CRISP_TEXT), ("ready_with_failures", CRISP_TEXT), ("ready", "Other text.")],
)
def test_set_reference_refuses_ineligible_job(client, status, style_text):
    job_id = add_job(STUB_SONG_ID, status=status, style_id=CRISP_MODERN_ID, style_text=style_text)

    response = client.post(f"/api/styles/{CRISP_MODERN_ID}/reference", json={"jobId": job_id})

    assert response.status_code == 409
    assert response.json()["error"] == "not_eligible"
    assert _reference_of(client, CRISP_MODERN_ID) is None


@pytest.mark.parametrize(
    "style_id, job_id, error",
    [("nope", "nope", "style_not_found"), (CRISP_MODERN_ID, "nope", "job_not_found")],
)
def test_set_reference_unknown_style_or_job(client, style_id, job_id, error):
    response = client.post(f"/api/styles/{style_id}/reference", json={"jobId": job_id})

    assert response.status_code == 404
    assert response.json()["error"] == error


def test_set_reference_takes_only_a_job_of_ours(client):
    body = {"videoUrl": "https://example.com/creator-tour.mp4"}

    response = client.post(f"/api/styles/{CRISP_MODERN_ID}/reference", json=body)

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert _reference_of(client, CRISP_MODERN_ID) is None


def test_get_reproduction_side_by_side(client):
    reference = _with_reference()
    add_shots(reference, [3.0, 3.0, 3.0])
    add_cut_check(reference, 2, 3.0, 3.04)
    add_cut_check(reference, 3, 6.0, 5.88)
    job_id = _golden_job(label="48 Elm Road")
    add_shots(job_id, [2.5, 2.5, 2.5, 2.5])
    add_cut_check(job_id, 2, 2.5, 2.45)

    response = _compare(client, job_id)

    body = response.json()
    assert response.status_code == 200
    assert body["reference"]["jobId"] == reference
    assert f"jobs/{reference}/video-v1.mp4" in body["reference"]["videoUrl"]
    assert body["reference"]["photoshootLabel"] == "12 Oak Street"
    assert body["reproduction"]["jobId"] == job_id
    assert f"jobs/{job_id}/video-v1.mp4" in body["reproduction"]["videoUrl"]
    assert body["reproduction"]["photoshootLabel"] == "48 Elm Road"
    assert set(body["summary"]["reference"]) == SUMMARY_KEYS
    assert set(body["summary"]["reproduction"]) == SUMMARY_KEYS
    assert [row["position"] for row in body["shots"]] == [1, 2, 3, 4]
    assert body["shots"][1]["reference"] == {"lengthS": 3.0, "cutErrorS": 0.04}
    assert body["shots"][1]["reproduction"] == {"lengthS": 2.5, "cutErrorS": -0.05}
    assert body["shots"][3]["reference"] is None
    assert body["maxCutErrorS"] == 0.12


def test_summaries_count_shots_movements_and_transitions(client):
    reference = _with_reference()
    for position, (length, movement, transition) in enumerate(
        [
            (2.0, "dolly_in", "cut"),
            (3.0, "crane_up", "cut"),
            (3.0, "dolly_in", "crossfade"),
            (4.0, "crane_up", "cut"),
            (4.0, "dolly_in", "cut"),
            (4.0, "crane_up", "crossfade"),
            (5.0, "dolly_in", "cut"),
        ],
        start=1,
    ):
        add_shot(reference, position, length, transition=transition, movement=movement)
    job_id = _golden_job(label="48 Elm Road")
    add_shots(job_id, [3.0, 3.0, 3.5, 4.0, 4.0, 4.5])

    summary = _compare(client, job_id).json()["summary"]

    assert summary["reference"] == {
        "shotCount": 7,
        "totalS": 25.0,
        "medianShotS": 4.0,
        "movements": {"dolly_in": 4, "crane_up": 3},
        "transitions": {"cut": 4, "crossfade": 2},
    }
    assert summary["reproduction"] == {
        "shotCount": 6,
        "totalS": 22.0,
        "medianShotS": 3.75,
        "movements": {"dolly_in": 6},
        "transitions": {"cut": 5},
    }


@pytest.mark.parametrize(
    "change",
    [
        {"model": "google/veo-3.1", "model_used": "bytedance/seedance-2.0"},
        {"edited_at": "2026-10-19T12:00:00.000Z"},
        {"removed": 1},
    ],
    ids=["fallback", "edited", "removed"],
)
def test_flagged_reproduction_shot(client, change):
    reference = _with_reference()
    add_shots(reference, [3.0] * 4)
    job_id = _golden_job(label="48 Elm Road")
    for position in (1, 2, 4):
        add_shot(job_id, position)
    add_shot(job_id, 3, **change)

    shots = _compare(client, job_id).json()["shots"]

    assert [row["flagged"] for row in shots] == [False, False, True, False]


def test_get_reproduction_without_reference(client):
    job_id = add_job(STUB_SONG_ID, style_id=CRISP_MODERN_ID, style_text=CRISP_TEXT)

    response = _compare(client, job_id, CRISP_MODERN_ID)

    assert response.status_code == 409
    assert response.json()["error"] == "no_reference"


@pytest.mark.parametrize("unchanged", [True, False])
def test_song_and_text_are_compared(client, unchanged):
    _with_reference()
    other_song = add_song(title="Night Drive", artist="Artist B")
    song_id, text = (STUB_SONG_ID, GOLDEN_TEXT) if unchanged else (other_song, "Faster, please.")
    job_id = add_job(song_id, style_id=GOLDEN_HOUR_ID, style_text=text)
    credit = next(song.credit for song in library.list_songs() if song.id == song_id)

    body = _compare(client, job_id).json()

    assert body["song"] == {"sameSong": unchanged, "credit": credit}
    assert body["sameText"] is unchanged


@pytest.mark.parametrize(
    "style_id, job_id, status, error",
    [
        ("nope", "nope", 404, "style_not_found"),
        (CRISP_MODERN_ID, "nope", 404, "job_not_found"),
        (CRISP_MODERN_ID, "ready-job", 409, "no_reference"),
    ],
)
def test_get_reproduction_error_order(client, style_id, job_id, status, error):
    ready_job = _golden_job()
    job_id = ready_job if job_id == "ready-job" else job_id

    response = _compare(client, job_id, style_id)

    assert response.status_code == status
    assert response.json()["error"] == error


@pytest.mark.parametrize(
    "reference_kwargs, job_kwargs",
    [({"status": "running"}, {}), ({}, {"video_key": None}), ({}, {"status": "queued"})],
)
def test_get_reproduction_not_ready(client, reference_kwargs, job_kwargs):
    _with_reference(**reference_kwargs)
    job_id = _golden_job(label="48 Elm Road", **job_kwargs)

    response = _compare(client, job_id)

    assert response.status_code == 409
    assert response.json()["error"] == "not_ready"
