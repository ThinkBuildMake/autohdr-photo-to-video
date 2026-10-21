import pytest

from app.pipeline import run
from tests.pipeline import run_world
from tests.pipeline.clip_world import BUCKET, flagged_check
from tests.pipeline.run_world import at

SIX = [{"position": p} for p in range(1, 7)]


@pytest.mark.parametrize(("minutes", "more_clips"), [(29, False), (27, True)])
def test_no_clip_after_the_deadline(monkeypatch, tmp_path, minutes, more_clips):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)
    world.checks[5] = [flagged_check()]
    world.clock_at_generate[5] = at(minutes)
    job = world.claim()

    world.run_shots(job)

    shots = world.shots(job_id)
    if more_clips:
        assert world.generated == [1, 2, 3, 4, 5, 5, 6]
        assert shots[5]["status"] == "passed"
    else:
        assert world.generated == [1, 2, 3, 4, 5]
        assert (shots[5]["status"], shots[5]["failure_reason"]) == ("failed", "out_of_time")
        assert (shots[6]["status"], shots[6]["failure_reason"]) == ("failed", "out_of_time")
        assert shots[5]["status_detail"] == "Ran out of time."
    assert [shots[p]["status"] for p in range(1, 5)] == ["passed"] * 4


def test_out_of_credit_stops_the_job(monkeypatch, tmp_path):
    world = run_world.install(monkeypatch, tmp_path)
    job_id = world.seed(SIX)
    world.generate[3] = ["out_of_credit"]
    job = world.claim()

    run.finish_run(world.run_shots(job), tmp_path / "finish")

    assert world.generated == [1, 2, 3]
    assert world.assembled == []
    assert world.cuts == []
    row = world.job(job_id)
    assert (row["status"], row["stop_reason"]) == ("stopped", "out_of_credit")
    shots = world.shots(job_id)
    for position in (1, 2):
        assert shots[position]["status"] == "passed"
        assert shots[position]["clip_key"] in BUCKET
    for position in (3, 4, 5, 6):
        assert (shots[position]["status"], shots[position]["failure_reason"]) == (
            "failed",
            "job_stopped",
        )
