import pytest

from app.config import reset_settings
from app.pipeline import clip
from tests.pipeline import clip_world
from tests.pipeline.clip_world import make_shot

JOB = "J"
VEO = "google/veo-3.1"
SEEDANCE = "bytedance/seedance-2.0"


def run(shot, tmp_path):
    return clip.make_clip(JOB, shot, 0, b"jpeg", "a prompt", 4.0, tmp_path)


def models(world, shot):
    return [a["model"] for a in world.attempts(shot.id)]


def test_refusal_moves_to_the_fallback_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4)
    world.generate[shot.id] = ["refused"]

    assert run(shot, tmp_path) == "att-4-2"

    assert models(world, shot) == [VEO, SEEDANCE]
    assert [g["model"] for g in world.named("generate_clip")] == [VEO, SEEDANCE]
    names = world.names()
    second_start = [i for i, n in enumerate(names) if n == "start_attempt"][1]
    detail = world.events[second_start - 1][1]["detail"]
    assert "fallback" in detail and SEEDANCE in detail
    checking = [d for s, d in world.details(shot.id) if s == "checking"]
    assert checking and SEEDANCE in checking[0]
    assert world.result(shot.id) == {
        "shot": shot.id,
        "result": "passed",
        "failure_reason": None,
        "final_attempt_id": "att-4-2",
    }


def test_two_failures_move_to_the_fallback_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(5)
    world.generate[shot.id] = ["failed", "failed"]

    assert run(shot, tmp_path) == "att-5-3"

    assert models(world, shot) == [VEO, VEO, SEEDANCE]
    assert [g["model"] for g in world.named("generate_clip")] == [VEO, VEO, SEEDANCE]


def test_one_failure_stays_on_the_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(5)
    world.generate[shot.id] = ["failed"]

    assert run(shot, tmp_path) == "att-5-2"

    assert models(world, shot) == [VEO, VEO]
    assert not any("fallback" in d for _, d in world.details(shot.id))


def test_fallback_refusal_fails_the_shot(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = ["refused", "refused"]

    assert run(shot, tmp_path) is None

    assert models(world, shot) == [VEO, SEEDANCE]
    assert world.result(shot.id) == {
        "shot": shot.id,
        "result": "failed",
        "failure_reason": "refused",
        "final_attempt_id": None,
    }


def test_shot_planned_on_the_fallback_fails_at_the_first_refusal(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(2, model=SEEDANCE)
    world.generate[shot.id] = ["refused"]

    assert run(shot, tmp_path) is None

    assert models(world, shot) == [SEEDANCE]
    assert world.result(shot.id)["failure_reason"] == "refused"
    assert not any("fallback" in d for _, d in world.details(shot.id))


def test_failures_on_the_fallback_do_not_fail_the_shot_early(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(3)
    world.generate[shot.id] = ["refused", "failed", "failed"]

    assert run(shot, tmp_path) == "att-3-4"

    assert models(world, shot) == [VEO, SEEDANCE, SEEDANCE, SEEDANCE]


@pytest.mark.parametrize("kind", ["rate_limited", "timeout", "bad_response"])
def test_other_errors_never_switch_the_model(monkeypatch, tmp_path, kind):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = [kind, kind, kind]

    assert run(shot, tmp_path) == "att-1-4"

    assert models(world, shot) == [VEO] * 4


def test_check_error_never_switches_the_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.checks[shot.id] = ["refused", "failed"]

    assert run(shot, tmp_path) == "att-1-3"

    assert models(world, shot) == [VEO] * 3


def test_env_override_names_the_fallback(monkeypatch, tmp_path):
    with monkeypatch.context() as scoped:
        scoped.setenv("VIDEO_MODEL_FALLBACK", "other/video-model")
        reset_settings()
        try:
            world = clip_world.install(scoped)
            shot = make_shot(4)
            world.generate[shot.id] = ["refused"]

            assert run(shot, tmp_path) == "att-4-2"

            assert models(world, shot) == [VEO, "other/video-model"]
            assert world.named("generate_clip")[1]["model"] == "other/video-model"
        finally:
            reset_settings()
    reset_settings()


@pytest.mark.parametrize(
    "earlier",
    [[(VEO, "refused")], [(VEO, "failed"), (VEO, "failed")]],
)
def test_resumed_round_keeps_the_fallback(monkeypatch, tmp_path, earlier):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=len(earlier))

    clip.make_clip(JOB, shot, 0, b"jpeg", "a prompt", 4.0, tmp_path, earlier)

    assert models(world, shot) == [SEEDANCE]


def test_resumed_round_after_one_failure_stays_on_the_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=1)

    clip.make_clip(JOB, shot, 0, b"jpeg", "a prompt", 4.0, tmp_path, [(VEO, "failed")])

    assert models(world, shot) == [VEO]


def test_resumed_shot_marked_as_using_the_fallback_keeps_it(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=2, used_fallback=True)

    clip.make_clip(JOB, shot, 0, b"jpeg", "a prompt", 4.0, tmp_path)

    assert models(world, shot) == [SEEDANCE]


def test_fallback_uses_its_own_allowed_duration(monkeypatch, tmp_path):
    from app.providers import interface as providers

    world = clip_world.install(monkeypatch)
    shot = make_shot(4, length_s=5)
    world.generate[shot.id] = ["refused"]
    monkeypatch.setattr(providers, "allowed_lengths", lambda model: [4, 8] if model == VEO else [6])

    run(shot, tmp_path)

    assert [a["requested_s"] for a in world.attempts(shot.id)] == [8, 6]


def test_empty_allowed_lengths_fail_clearly(monkeypatch):
    from app.pipeline import prompt
    from app.providers import interface as providers

    monkeypatch.setattr(providers, "allowed_lengths", lambda model: [])
    with pytest.raises(ValueError, match="no allowed clip lengths"):
        prompt.clip_length(make_shot(1))


def test_resumed_check_error_never_switches_model(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=2)

    clip.make_clip(
        JOB,
        shot,
        0,
        b"jpeg",
        "prompt",
        4,
        tmp_path,
        [(VEO, "check_error:refused"), (VEO, "check_error:failed")],
    )

    assert models(world, shot) == [VEO]


def test_resumed_all_flagged_round_keeps_failure_reason(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=4)

    clip.make_clip(JOB, shot, 0, b"jpeg", "prompt", 4, tmp_path, [(VEO, "flagged")] * 4)

    assert world.attempts(shot.id) == []
    assert world.result(shot.id)["failure_reason"] == "flagged_every_attempt"
