import uuid

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.jobs import stubs
from app.jobs.plan_rules import MOVEMENTS, renumber, validate_plan
from app.shared.enums import MovementName
from app.shared.types import PlannedShot

VEO = "google/veo-3.1"
PHOTOS = {f"p{i}" for i in range(1, 7)}


def _shot(n, **over):
    base = dict(
        position=n,
        room="living",
        photo_id=f"p{n}",
        photo_edit_prompts=[],
        movement_name="dolly_in",
        movement_prompt="x",
        speed="slow",
        model=VEO,
        length_s=4.0,
        transition="cut",
        transition_s=0.0,
        plan_note="n",
    )
    base.update(over)
    return PlannedShot(**base)


def _plan():
    return [_shot(n) for n in range(1, 7)]


def _lengths(model: str) -> list[float]:
    if model == VEO:
        return [4.0, 6.0, 8.0]
    return []


def _check(shots, photos=PHOTOS, budget=60.0):
    return validate_plan(shots, photos, budget, _lengths)


def test_movements_cover_every_name_with_prd_texts():
    assert set(MOVEMENTS) == {m.value for m in MovementName}
    assert len(MOVEMENTS) == 12
    assert MOVEMENTS["crane_up"] == (
        "Super smooth camera rises vertically upward, straight vertical path, cinematic"
    )


def test_valid_plan_has_no_problems():
    assert _check(_plan()) == []


def test_unknown_movement_names_the_shot():
    problems = _check(_plan_with(2, movement_name="spin_around"))
    assert len(problems) == 1
    assert problems[0].startswith("Shot 2:") and "unknown movement" in problems[0]


def _plan_with(n, **over):
    shots = _plan()
    shots[n - 1] = _shot(n, **over)
    return shots


def test_length_over_longest_clip():
    problems = _check(_plan_with(2, length_s=12.0))
    assert problems == ["Shot 2: 12 s is longer than google/veo-3.1's longest clip, 8 s."]


def test_crossfade_counts_toward_clip_length():
    assert _check(_plan_with(2, length_s=4.0, transition="crossfade", transition_s=1.0)) == []
    problems = _check(_plan_with(2, length_s=8.0, transition="crossfade", transition_s=1.0))
    assert len(problems) == 1 and problems[0].startswith("Shot 2:") and "9 s" in problems[0]


def test_speed_transition_and_length_rules():
    assert "unknown speed" in _check(_plan_with(1, speed="warp"))[0]
    assert "unknown transition" in _check(_plan_with(1, transition="wipe"))[0]
    assert "cut" in _check(_plan_with(1, transition_s=0.5))[0]
    assert "crossfade" in _check(_plan_with(1, transition="crossfade", transition_s=0.0))[0]
    assert "length" in _check(_plan_with(1, length_s=0.0))[0]


def test_unknown_model():
    problems = _check(_plan_with(3, model="nope/model"))
    assert len(problems) == 1 and problems[0].startswith("Shot 3:") and "model" in problems[0]


def test_photo_not_in_shoot_is_named():
    problems = _check(_plan_with(4, photo_id="elsewhere"))
    assert len(problems) == 1
    assert problems[0].startswith("Shot 4:") and "elsewhere" in problems[0]


def test_total_over_song_budget():
    problems = _check(_plan(), budget=20.0)
    assert len(problems) == 1 and "24 s" in problems[0] and "20 s" in problems[0]


def test_null_photo_is_accepted_and_not_counted():
    shots = _plan_with(6, photo_id=None)
    assert _check(shots, budget=20.0) == []


def test_no_shots():
    assert len(_check([])) == 1


def test_renumber_sorts_and_numbers_from_one():
    shots = [_shot(7), _shot(2), _shot(5)]
    out = renumber(shots)
    assert [s.position for s in out] == [1, 2, 3]
    assert [s.photo_id for s in out] == ["p2", "p5", "p7"]


@pytest.fixture
def shoot():
    init_db()
    shoot_id = str(uuid.uuid4())
    with session_scope() as session:
        session.execute(
            text("insert into photoshoots (id, label, status) values (:i, 'S', 'ready')"),
            {"i": shoot_id},
        )
    return shoot_id


def test_photoshoot_status(shoot):
    assert stubs.photoshoot_status(shoot) == "ready"
    assert stubs.photoshoot_status("unknown") is None


@pytest.mark.parametrize("field", ["length_s", "transition_s"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_numbers_are_refused(field, value):
    over = {field: value}
    if field == "transition_s":
        over["transition"] = "crossfade"
    problems = _check(_plan_with(2, **over))
    assert problems
    assert all(p.startswith("Shot 2:") or p.startswith("The shots total") for p in problems)
    assert any("finite" in p for p in problems)
