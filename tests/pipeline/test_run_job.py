import threading
from pathlib import Path

import pytest

from app.config import get_settings, reset_settings
from app.jobs import worker_interface
from app.pipeline import runner
from app.providers import interface as providers
from app.shared.types import Job
from tests.pipeline import shot_world
from tests.pipeline.clip_world import make_shot

LOCK_TEXT = (
    "There are no people anywhere in the frame, and no reflections of people, cameras or "
    "photographers in any mirror or glass. Reflections in mirrors and glass must show only the "
    "same room contents as the photo. Keep exactly the same number of ceiling vents, lights and "
    "fixtures as the photo; do not add any."
)


def make_job(shots) -> Job:
    return Job(
        id="J",
        style_id=None,
        style_name="Custom style",
        photoshoot_id="S",
        purpose="video",
        style_text="Slow and warm.",
        plan_status="ready",
        plan_notes=None,
        status="running",
        stop_reason=None,
        submitted_at=None,
        started_at=None,
        finished_at=None,
        elapsed_s=0.0,
        total_cost_usd=0.0,
        waiting_behind=None,
        shots=shots,
        video=None,
        song_credit="",
    )


@pytest.fixture
def world(monkeypatch):
    world = shot_world.install(monkeypatch)
    monkeypatch.setattr(providers, "allowed_lengths", lambda model: [4.0, 6.0, 8.0])
    return world


def claims(monkeypatch, *shots):
    monkeypatch.setattr(worker_interface, "claim_next_job", lambda: make_job(list(shots)))


def in_flight(monkeypatch, n):
    monkeypatch.setenv("SHOTS_IN_FLIGHT", str(n))
    reset_settings()


def requested(world, shot):
    return world.attempts(shot.id)[0]["requested_s"]


def test_nothing_to_claim_returns_false(world, monkeypatch):
    monkeypatch.setattr(worker_interface, "claim_next_job", lambda: None)

    assert runner.run_next_job() is False


def test_every_shot_runs_at_once(world, monkeypatch):
    shots = [make_shot(n) for n in range(1, 7)]
    claims(monkeypatch, *shots)
    in_flight(monkeypatch, 6)
    all_six = threading.Barrier(6, timeout=5)
    world.on_photo = lambda photo_id: all_six.wait()

    assert runner.run_next_job() is True

    names = world.names()
    first_finish = names.index("set_shot_result")
    assert names[:first_finish].count("get_photo") == 6
    assert [world.result(s.id)["result"] for s in shots] == ["passed"] * 6


def test_shots_in_flight_is_a_cap(world, monkeypatch):
    shots = [make_shot(n) for n in range(1, 7)]
    claims(monkeypatch, *shots)
    in_flight(monkeypatch, 2)
    three = threading.Barrier(3, timeout=0.5)
    filled = []

    def wait_for_a_third(photo_id):
        try:
            three.wait()
            filled.append(True)
        except threading.BrokenBarrierError:
            pass

    world.on_photo = wait_for_a_third

    runner.run_next_job()

    assert filled == []
    active = peak = 0
    for name in world.names():
        active += {"get_photo": 1, "set_shot_result": -1}.get(name, 0)
        peak = max(peak, active)
    assert peak == 2
    assert [world.result(s.id)["result"] for s in shots] == ["passed"] * 6


def test_one_failing_shot_does_not_stop_the_others(world, monkeypatch, caplog):
    shots = [make_shot(n) for n in range(1, 4)]
    claims(monkeypatch, *shots)

    def fail_shot_two(photo_id):
        if photo_id == shots[1].photo_id:
            raise OSError("disk full")

    world.on_photo = fail_shot_two

    runner.run_next_job()

    assert [world.result(s.id) is not None for s in shots] == [True, True, True]
    assert world.result(shots[1].id)["failure_reason"] == "provider_error"
    (logged,) = [r for r in caplog.records if r.name == "app.pipeline.run"]
    assert logged.levelname == "ERROR"
    assert logged.getMessage() == f"shot {shots[1].id} failed"
    assert isinstance(logged.exc_info[1], OSError)


def test_full_prompt_is_stored(world, monkeypatch):
    shot = make_shot(
        1,
        movement_name="dolly_in",
        movement_prompt=(
            "Super smooth camera moves forward in straight line through space, cinematic"
        ),
        speed="slow",
    )
    claims(monkeypatch, shot)

    runner.run_next_job()

    assert world.attempts(shot.id)[0]["prompt"] == (
        "Super smooth camera moves forward in straight line through space, cinematic. "
        "Camera speed: slow. " + LOCK_TEXT
    )


def test_clip_length_covers_the_shot(world, monkeypatch):
    shot = make_shot(2, length_s=4.5, transition="crossfade", transition_s=0.5)
    claims(monkeypatch, make_shot(1), shot)

    runner.run_next_job()

    assert requested(world, shot) == 6.0


def test_first_shot_ignores_its_transition(world, monkeypatch):
    first = make_shot(1, length_s=4.0, transition="crossfade", transition_s=0.5)
    second = make_shot(2, length_s=4.0, transition="crossfade", transition_s=0.5)
    claims(monkeypatch, first, second)

    runner.run_next_job()

    assert (requested(world, first), requested(world, second)) == (4.0, 6.0)


def test_first_pending_shot_of_a_redo_keeps_its_crossfade(world, monkeypatch):
    redone = make_shot(3, length_s=4.0, transition="crossfade", transition_s=0.5)
    claims(monkeypatch, redone)

    runner.run_next_job()

    assert requested(world, redone) == 6.0


def test_temporary_files_stay_off_the_volume(world, monkeypatch):
    volume = Path(get_settings().DATABASE_PATH).resolve().parent
    before = sorted(volume.rglob("*"))
    shots = [make_shot(1, photo_edit_prompts=["Brighten the room"]), make_shot(2)]
    claims(monkeypatch, *shots)

    runner.run_next_job()

    paths = [Path(p["path"]).resolve() for p in world.named("put")]
    assert len(paths) == 5  # 2 crops, 1 edit, 2 clips
    assert not any(p.is_relative_to(volume) for p in paths)
    assert not any(p.exists() for p in paths)
    assert not any(p.parent.exists() for p in paths)
    assert sorted(volume.rglob("*")) == before
