from pathlib import Path

import pytest

from app.jobs.errors import AttemptLimitReached
from app.media.errors import MediaError
from app.pipeline import clip, clip_stubs
from app.providers.errors import ProviderError
from app.shared.enums import ProviderErrorKind
from tests.pipeline import clip_world
from tests.pipeline.clip_world import flagged_check, make_shot, passed_check

JOB = "J"


def run(world, shot, tmp_path, round_no=0):
    return clip.make_clip(JOB, shot, round_no, b"jpeg", "a prompt", 4.0, tmp_path)


def test_flagged_clip_is_tried_again(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(2)
    world.checks[shot.id] = [flagged_check("looks AI-made"), passed_check()]

    result = run(world, shot, tmp_path)

    assert result == "att-2-2"
    assert len(world.attempts(shot.id)) == 2
    first, second = world.finishes(shot.id)
    assert (first["attempt_id"], first["status"]) == ("att-2-1", "flagged")
    assert first["clip_key"] == "jobs/J/shots/2/r0/a1.mp4"
    assert first["check"].ai_score == 0.8
    assert (second["attempt_id"], second["status"]) == ("att-2-2", "passed")
    assert second["clip_key"] == "jobs/J/shots/2/r0/a2.mp4"
    assert world.result(shot.id) == {
        "shot": shot.id,
        "result": "passed",
        "failure_reason": None,
        "final_attempt_id": "att-2-2",
    }
    assert "jobs/J/shots/2/r0/a2.mp4" in clip_stubs.BUCKET


def test_four_flags_fail_the_shot(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(3)
    world.checks[shot.id] = [flagged_check(ai_score=0.5 + i / 10) for i in range(4)]

    result = run(world, shot, tmp_path)

    assert result is None
    assert len(world.attempts(shot.id)) == 4
    assert len(world.named("generate_clip")) == 4
    assert len(world.named("check_clip")) == 4
    finishes = world.finishes(shot.id)
    assert [f["status"] for f in finishes] == ["flagged"] * 4
    assert [f["check"].ai_score for f in finishes] == [0.5, 0.6, 0.7, 0.8]
    assert world.result(shot.id)["result"] == "failed"
    assert world.result(shot.id)["failure_reason"] == "flagged_every_attempt"
    assert world.result(shot.id)["final_attempt_id"] is None
    assert [r["result"] for r in world.named("set_shot_result")] == ["failed"]


def test_rate_limit_counts_as_an_attempt(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = [ProviderError("rate_limited", "429", retry_after_s=7), None]

    result = run(world, shot, tmp_path)

    assert result == "att-1-2"
    names = world.names()
    first_finish = world.finishes(shot.id)[0]
    assert (first_finish["attempt_id"], first_finish["status"]) == ("att-1-1", "error")
    assert first_finish["error"].kind == ProviderErrorKind.rate_limited
    busy = ("generating", "Provider busy, trying again")
    assert busy in world.details(shot.id)
    busy_at = names.index("set_shot_state", names.index("finish_attempt"))
    assert world.events[busy_at][1]["detail"] == busy[1]
    assert busy_at < [i for i, n in enumerate(names) if n == "start_attempt"][1]
    assert [a["seconds"] for a in world.named("wait")] == [7]
    assert world.result(shot.id)["final_attempt_id"] == "att-1-2"


def test_busy_every_time_stops_at_four(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = ["rate_limited", "timeout", "rate_limited", "timeout"]

    assert run(world, shot, tmp_path) is None

    assert len(world.attempts(shot.id)) == 4
    assert world.result(shot.id)["failure_reason"] == "provider_error"
    assert [a["seconds"] for a in world.named("wait")] == [5.0] * 3


def test_busy_wait_is_capped(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = [ProviderError("rate_limited", "429", retry_after_s=600), None]

    run(world, shot, tmp_path)

    assert [a["seconds"] for a in world.named("wait")] == [30.0]


@pytest.mark.parametrize("where", ["generate", "check"])
def test_error_is_written_at_once(monkeypatch, tmp_path, where):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    error = ProviderError("failed", "boom")
    if where == "generate":
        world.generate[shot.id] = [error]
    else:
        world.checks[shot.id] = [error]

    assert run(world, shot, tmp_path) == "att-1-2"

    failure = "generate_failed" if where == "generate" else "check_failed"
    index = world.names().index(failure)
    name, args, finished_at = world.events[index + 1]
    assert name == "finish_attempt"
    assert (args["attempt_id"], args["status"]) == ("att-1-1", "error")
    assert args["error"].kind == ProviderErrorKind.failed
    assert finished_at - world.events[index][2] < 60


@pytest.mark.parametrize(
    "generate, checks, reason",
    [
        (["failed"] * 4, [], "provider_error"),
        (["rate_limited", None, None, None], [None, flagged_check(), flagged_check()], None),
        (["refused", "failed", "failed", "timeout"], [], "provider_error"),
        ([None] * 4, [flagged_check()] * 4, "flagged_every_attempt"),
        (["failed", None, "timeout", None], [flagged_check(), flagged_check()], None),
    ],
)
def test_never_more_than_four_attempts(monkeypatch, tmp_path, generate, checks, reason):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4)
    world.generate[shot.id] = generate
    world.checks[shot.id] = [c or passed_check() for c in checks]

    run(world, shot, tmp_path)

    assert len(world.attempts(shot.id)) <= clip.MAX_ATTEMPTS
    if reason:
        assert world.result(shot.id)["failure_reason"] == reason


def test_flag_after_errors_is_not_reported_as_flagged_every_attempt(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(5)
    world.generate[shot.id] = ["timeout", "failed", "timeout", None]
    world.checks[shot.id] = [flagged_check()]

    assert run(world, shot, tmp_path) is None

    assert len(world.attempts(shot.id)) == 4
    assert world.result(shot.id)["failure_reason"] == "provider_error"


def test_resumed_round_has_only_the_attempts_left(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4, attempts=1)
    world.checks[shot.id] = [flagged_check()] * 5

    assert run(world, shot, tmp_path) is None

    assert len(world.attempts(shot.id)) == 3
    assert world.result(shot.id)["failure_reason"] == "flagged_every_attempt"


def test_attempt_limit_ends_the_loop(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(4)

    def limit(*args):
        world.record("start_attempt_refused", shot=shot.id)
        raise AttemptLimitReached()

    monkeypatch.setattr(clip_stubs, "start_attempt", limit)

    assert run(world, shot, tmp_path) is None

    assert world.names().count("start_attempt_refused") == 1
    assert "generate_clip" not in world.names()
    assert world.result(shot.id)["result"] == "failed"
    assert world.result(shot.id)["failure_reason"] == "provider_error"


@pytest.mark.parametrize(
    "script",
    [
        {"checks": [flagged_check()] * 4},
        {"checks": [ProviderError("failed", "x")] * 4},
        {"frame_errors": [MediaError("bad")] * 4},
        {"checks": [flagged_check(ai_score=0.0)] * 4},
    ],
)
def test_only_a_passed_check_is_used(monkeypatch, tmp_path, script):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.checks[shot.id] = script.get("checks", [])
    world.frame_errors[shot.id] = script.get("frame_errors", [])

    assert run(world, shot, tmp_path) is None

    assert all(r["result"] != "passed" for r in world.named("set_shot_result"))
    assert all(f["status"] != "passed" for f in world.finishes())


def test_passed_result_follows_its_passed_attempt(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.checks[shot.id] = [flagged_check(), passed_check()]

    run(world, shot, tmp_path)

    passed = [f["attempt_id"] for f in world.finishes() if f["status"] == "passed"]
    result = world.named("set_shot_result")[0]
    assert passed == [result["final_attempt_id"]]
    names = world.names()
    assert names.index("set_shot_result") > max(
        i for i, n in enumerate(names) if n == "finish_attempt"
    )


def test_unreadable_clip_is_recorded_as_a_bad_response(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.frame_errors[shot.id] = [MediaError("ffmpeg")]

    assert run(world, shot, tmp_path) == "att-1-2"

    first = world.finishes(shot.id)[0]
    assert first["status"] == "error"
    assert first["error"].kind == ProviderErrorKind.bad_response
    assert first["cost_usd"] == 0.25


def test_every_error_reaches_the_shot_before_waiting(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = [ProviderError("rate_limited", "429", retry_after_s=25), None]

    run(world, shot, tmp_path)

    names = world.names()
    assert names.index("finish_attempt") < names.index("wait")
    assert world.events[names.index("generate_failed") + 1][0] == "finish_attempt"
    assert [a["seconds"] for a in world.named("wait")] == [25]


def test_out_of_credit_is_recorded_then_raised(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    world.generate[shot.id] = ["out_of_credit", None]

    with pytest.raises(ProviderError) as raised:
        run(world, shot, tmp_path)

    assert raised.value.kind == ProviderErrorKind.out_of_credit
    finishes = world.finishes(shot.id)
    assert [(f["status"], f["error"].kind) for f in finishes] == [
        ("error", ProviderErrorKind.out_of_credit)
    ]
    assert len(world.attempts(shot.id)) == 1
    assert world.named("set_shot_result") == []


def test_clip_files_stay_in_the_folder(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    folder = tmp_path / "job"
    folder.mkdir()
    world.checks[shot.id] = [flagged_check(), passed_check()]

    clip.make_clip(JOB, shot, 0, b"jpeg", "a prompt", 4.0, folder)

    assert world.clip_paths
    assert not any(Path(p).exists() for p in world.clip_paths)
    assert sorted(p.name for p in folder.iterdir()) == ["a1.mp4", "a2.mp4"]
    ids = [e["ids"] for e in world.named("generate_clip") + world.named("check_clip")]
    assert len(ids) == 4
    for given in ids:
        assert given["jobId"] == JOB
        assert given["jobShotId"] == shot.id
        assert given["attemptId"].startswith("att-1-")


@pytest.mark.parametrize("retry_after", [-3, float("nan"), float("inf"), float("-inf")])
def test_odd_retry_after_uses_the_default_wait(monkeypatch, tmp_path, retry_after):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1)
    busy = ProviderError("rate_limited", "429", retry_after_s=retry_after)
    world.generate[shot.id] = [busy, None]

    assert run(world, shot, tmp_path) == "att-1-2"

    assert [a["seconds"] for a in world.named("wait")] == [5.0]


def test_no_wait_after_the_last_busy_answer(monkeypatch, tmp_path):
    world = clip_world.install(monkeypatch)
    shot = make_shot(1, attempts=3)
    world.generate[shot.id] = ["rate_limited"]

    assert run(world, shot, tmp_path) is None

    assert world.named("wait") == []
    assert world.result(shot.id)["failure_reason"] == "provider_error"
