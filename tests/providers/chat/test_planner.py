import json

import pytest

from app.db.base import session_scope
from app.jobs.models import Job
from app.library.models import Song
from app.providers import planner
from app.providers.errors import ProviderError
from app.shared.enums import Room
from app.shared.types import PlannedShot

MOVEMENTS = {
    "dolly_in": "Slow dolly in toward the focal point.",
    "parallax_orbit": "Gentle orbit around the room's centre.",
    "crane_up": "Crane up to reveal the whole space.",
}
NOTES = "The text asks for a pool; none in the photos."


def shot(photo_id, room, movement, position=1, **extra):
    return {
        "position": position,
        "room": room,
        "photoId": photo_id,
        "photoEditPrompts": ["brighten the room"],
        "movementName": movement,
        "movementPrompt": MOVEMENTS.get(movement, "x"),
        "speed": "slow",
        "model": "google/veo-3.1",
        "lengthS": 6,
        "transition": "crossfade",
        "transitionS": 0.5,
        "planNote": "opens on the island",
        **extra,
    }


PLAN = {
    "shots": [
        shot("p1", "kitchen", "dolly_in"),
        shot("p2", "bedroom", "parallax_orbit", 2),
        shot("p3", "living", "crane_up", 3),
    ],
    "notes": NOTES,
}


def photos(synthetic_jpeg):
    return [
        {
            "photoId": "p1",
            "room": "kitchen",
            "subject": "white island",
            "jpegBytes": synthetic_jpeg("tan", "k"),
        },
        {
            "photoId": "p2",
            "room": "bedroom",
            "subject": "queen bed",
            "jpegBytes": synthetic_jpeg("navy", "b"),
        },
        {
            "photoId": "p3",
            "room": "living",
            "subject": "sofa",
            "jpegBytes": synthetic_jpeg("gray", "l"),
        },
    ]


def seed_job():
    with session_scope() as session:
        session.add(
            Song(
                id="song",
                title="t",
                artist="a",
                licence_code="BY-NC",
                source_url="u",
                file_key="k",
                duration_s=60,
            )
        )
        session.flush()
        session.add(
            Job(
                id="job-1",
                style_text="x",
                photoshoot_id="ps-1",
                song_id="song",
                song_offset_s=0,
                fps=24,
            )
        )


@pytest.fixture
def job(openrouter):
    seed_job()
    return "job-1"


def run(synthetic_jpeg, movements=MOVEMENTS):
    return planner.plan_shots(
        "Warm and welcoming, show the pool.",
        40.0,
        photos(synthetic_jpeg),
        movements,
        [4, 6, 8],
        {"jobId": "job-1"},
    )


def test_plan_comes_back_in_shape(openrouter, job, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(json=chat_answer(json.dumps(PLAN)))

    result = run(synthetic_jpeg)

    assert result["notes"] == NOTES
    assert len(result["shots"]) == 3
    for index, planned in enumerate(result["shots"], start=1):
        assert isinstance(planned, PlannedShot)
        assert planned.position == index
        assert planned.photo_id == f"p{index}"
        assert planned.photo_edit_prompts == ["brighten the room"]
        assert planned.movement_name in MOVEMENTS
        assert planned.speed == "slow"
        assert planned.length_s == 6
        assert planned.transition == "crossfade"
    assert result["shots"][0].room == Room.kitchen
    body = openrouter.body()
    assert body["model"] == "anthropic/claude-sonnet-5.5"
    parts = body["messages"][0]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 3
    (row,) = rows()
    assert (row.kind, row.job_id, row.status) == ("plan_shots", "job-1", "ok")


def test_prose_plan_is_bad_response(openrouter, job, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(json=chat_answer("Here is a lovely plan: start in the kitchen..."))

    with pytest.raises(ProviderError) as caught:
        run(synthetic_jpeg)

    assert caught.value.kind == "bad_response"
    (row,) = rows()
    assert row.status == "error" and row.error_kind == "bad_response"


@pytest.mark.parametrize(
    "bad",
    [
        {"shots": [shot("nope", "kitchen", "dolly_in")], "notes": ""},
        {"shots": [shot("p1", "kitchen", "spin_around")], "notes": ""},
        {"shots": [shot("p1", "kitchen", "dolly_in", lengthS=0)], "notes": ""},
        {"shots": [], "notes": ""},
        {"notes": "no shots"},
        [shot("p1", "kitchen", "dolly_in")],
    ],
)
def test_unknown_photo_or_movement_is_bad_response(
    openrouter, job, chat_answer, synthetic_jpeg, rows, bad
):
    openrouter.answer(json=chat_answer(json.dumps(bad)))

    with pytest.raises(ProviderError) as caught:
        run(synthetic_jpeg)

    assert caught.value.kind == "bad_response"
    (row,) = rows()
    assert row.status == "error" and row.error_kind == "bad_response"


def test_planner_500_is_failed(openrouter, job, synthetic_jpeg, rows):
    openrouter.answer(status=500, json={"error": {"code": 500, "message": "upstream down"}})

    with pytest.raises(ProviderError) as caught:
        run(synthetic_jpeg)

    assert caught.value.kind == "failed"
    (row,) = rows()
    assert row.kind == "plan_shots" and row.error_kind == "failed"


@pytest.mark.live
def test_live_plan_shots(live, synthetic_jpeg):
    seed_job()
    result = run(synthetic_jpeg)
    assert result["shots"] and isinstance(result["notes"], str)
