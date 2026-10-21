import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import shot_writes, worker_interface
from app.jobs.errors import JobNotFound, JobNotRunning
from app.shared.types import Job
from tests.support.worker_rows import (
    add_attempt,
    add_job,
    add_provider_call,
    add_shot,
    row,
    rows,
    set_final_attempt,
)

VIDEO = {
    "key": "jobs/J/video-v1.mp4",
    "duration_s": 30.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
}


def race(call, n):
    """Run call() from n threads released together; returns the results."""
    barrier = threading.Barrier(n)
    results, errors = [], []

    def work():
        barrier.wait(timeout=10)
        try:
            results.append(call())
        except Exception as exc:  # noqa: BLE001 - reported through the assert below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert len(results) == n
    return results


def test_two_threads_claim_only_the_oldest(song, shoot):
    shoot_id, photos = shoot
    # OLD was drafted later but submitted earlier: creation order and submit order disagree.
    old = add_job(
        shoot_id,
        song,
        status="queued",
        submitted_at="2026-10-19T09:00:00.000Z",
        created_at="2026-10-19T08:59:00.000Z",
    )
    new = add_job(
        shoot_id,
        song,
        status="queued",
        submitted_at="2026-10-19T09:05:00.000Z",
        created_at="2026-10-19T08:00:00.000Z",
    )
    add_shot(old, 1, photos[0])
    add_shot(old, 2, photos[1])
    add_shot(old, 3, photos[2], status="passed")
    add_shot(new, 1, photos[0])

    results = race(worker_interface.claim_next_job, 2)

    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1 and results.count(None) == 1
    assert isinstance(claimed[0], Job)
    assert claimed[0].id == old
    assert claimed[0].status == "running"
    assert [s.position for s in claimed[0].shots] == [1, 2]
    assert row("jobs", old)["status"] == "running"
    assert row("jobs", new)["status"] == "queued"
    assert len(rows("select id from jobs where status = 'running'")) == 1


def test_claim_sets_the_30_minute_budget(song, shoot, clock):
    job = add_job(shoot[0], song, status="queued", submitted_at="2026-10-19T09:00:00.000Z")
    add_shot(job, 1, shoot[1][0])

    worker_interface.claim_next_job()

    claimed = row("jobs", job)
    assert claimed["started_at"] == "2026-10-19T10:00:00.000Z"
    assert claimed["deadline_at"] == "2026-10-19T10:30:00.000Z"


def test_claim_with_nothing_queued_returns_none(song, shoot):
    add_job(shoot[0], song, status="draft")
    assert worker_interface.claim_next_job() is None


def test_claimed_job_carries_song_credit_and_elapsed_time(song, shoot, clock):
    job = add_job(shoot[0], song, status="queued", submitted_at="2026-10-19T09:00:00.000Z")
    claimed = worker_interface.claim_next_job()
    assert claimed.id == job
    assert claimed.style_name == "Custom style"
    assert claimed.elapsed_s == 3600.0
    assert claimed.song_credit


def test_stop_keeps_passed_shots(running_job, shoot):
    photos = shoot[1]
    passed = []
    for position in (1, 2, 3):
        shot = add_shot(running_job, position, photos[position - 1], status="passed")
        attempt = add_attempt(shot, 1, status="passed")
        set_final_attempt(shot, attempt)

        passed.append((shot, attempt))
    generating = [add_shot(running_job, p, None, status="generating") for p in (4, 5)]
    live = [add_attempt(s, 1, status="running") for s in generating]

    worker_interface.stop_job(running_job, "out_of_credit")

    job = row("jobs", running_job)
    assert (job["status"], job["stop_reason"]) == ("stopped", "out_of_credit")
    assert job["finished_at"] is not None
    for shot, attempt in passed:
        kept = row("job_shots", shot)
        assert (kept["status"], kept["final_attempt_id"]) == ("passed", attempt)
    for shot, attempt in zip(generating, live, strict=True):
        failed = row("job_shots", shot)
        assert (failed["status"], failed["failure_reason"]) == ("failed", "job_stopped")
        assert (row("attempts", attempt)["status"], row("attempts", attempt)["error"]) == (
            "error",
            "job_stopped",
        )


def test_restart_stops_the_running_job(running_job, shoot):
    shot = add_shot(running_job, 1, shoot[1][0], status="generating")
    attempt = add_attempt(shot, 1, status="running")

    worker_interface.recover_interrupted()

    job = row("jobs", running_job)
    assert (job["status"], job["stop_reason"]) == ("stopped", "worker_restarted")
    assert job["finished_at"] is not None
    stopped = row("attempts", attempt)
    assert (stopped["status"], stopped["error"]) == ("error", "worker_restarted")
    assert stopped["finished_at"] is not None
    assert row("job_shots", shot)["failure_reason"] == "job_stopped"


def test_recover_changes_nothing_without_a_running_job(song, shoot):
    queued = add_job(shoot[0], song, status="queued", submitted_at="2026-10-19T09:00:00.000Z")
    worker_interface.recover_interrupted()
    assert row("jobs", queued)["status"] == "queued"


def requeue(job):
    with session_scope() as session:
        session.execute(text("update jobs set status='queued' where id=:i"), {"i": job})


def passed_shot(job, position, photo):
    shot = add_shot(job, position, photo, status="passed")
    return shot


def test_finish_totals_the_cost(running_job, shoot, clock):
    passed_shot(running_job, 1, shoot[1][0])
    add_provider_call(running_job, 1.20)
    add_provider_call(running_job, 0.40)
    other = add_job(shoot[0], rows("select id from songs")[0]["id"], status="draft")
    add_provider_call(other, 5.00)

    worker_interface.finish_job(running_job, "ready", video=VIDEO)

    job = row("jobs", running_job)
    assert job["status"] == "ready"
    assert job["total_cost_usd"] == pytest.approx(1.60)
    assert job["first_finished_at"] == job["finished_at"] == "2026-10-19T10:00:00.000Z"
    assert job["video_key"] == VIDEO["key"]
    assert job["video_version"] == 1


def test_ready_is_never_early(running_job, shoot):
    passed_shot(running_job, 1, shoot[1][0])
    add_shot(running_job, 2, shoot[1][1], status="generating")

    for status in ("ready", "ready_with_failures"):
        with pytest.raises(ValueError):
            worker_interface.finish_job(running_job, status, video=VIDEO)

    job = row("jobs", running_job)
    assert (job["status"], job["finished_at"], job["video_key"]) == ("running", None, None)


def test_ready_never_hides_a_failed_shot(running_job, shoot):
    passed_shot(running_job, 1, shoot[1][0])
    failed = add_shot(
        running_job, 2, shoot[1][1], status="failed", failure_reason="flagged_every_attempt"
    )

    with pytest.raises(ValueError):
        worker_interface.finish_job(running_job, "ready", video=VIDEO)
    assert row("jobs", running_job)["status"] == "running"

    worker_interface.finish_job(running_job, "ready_with_failures", video=VIDEO)
    assert row("jobs", running_job)["status"] == "ready_with_failures"
    assert row("job_shots", failed)["failure_reason"] == "flagged_every_attempt"


def test_stop_leaves_every_failed_shot_with_a_reason(running_job, shoot):
    add_shot(running_job, 1, shoot[1][0], status="pending")
    add_shot(running_job, 2, shoot[1][1], status="checking")
    worker_interface.stop_job(running_job, "no_shot_passed")
    failed = rows("select failure_reason from job_shots where status = 'failed'")
    assert len(failed) == 2 and all(r["failure_reason"] for r in failed)


def test_finish_needs_a_complete_video(running_job, shoot):
    passed_shot(running_job, 1, shoot[1][0])
    with pytest.raises(ValueError):
        worker_interface.finish_job(running_job, "ready", video={"key": "k"})
    with pytest.raises(ValueError):
        worker_interface.finish_job(running_job, "ready")
    with pytest.raises(ValueError):
        worker_interface.finish_job(running_job, "queued", video=VIDEO)
    assert row("jobs", running_job)["status"] == "running"


def test_finish_as_stopped_needs_a_stop_reason(running_job):
    with pytest.raises(ValueError):
        worker_interface.finish_job(running_job, "stopped")
    worker_interface.finish_job(running_job, "stopped", stop_reason="assembly_failed")
    job = row("jobs", running_job)
    assert (job["status"], job["stop_reason"], job["first_finished_at"]) == (
        "stopped",
        "assembly_failed",
        None,
    )


def test_reexport_is_a_new_version(song, shoot):
    job = add_job(
        shoot[0],
        song,
        status="queued",
        submitted_at="2026-10-19T09:40:00.000Z",
        video_key="jobs/J/video-v1.mp4",
        video_version=1,
        first_finished_at="2026-10-19T09:30:00.000Z",
    )
    passed_shot(job, 1, shoot[1][0])
    assert worker_interface.claim_next_job().id == job

    worker_interface.finish_job(job, "ready", video={**VIDEO, "key": "jobs/J/video-v2.mp4"})

    done = row("jobs", job)
    assert done["video_version"] == 2
    assert done["video_key"] == "jobs/J/video-v2.mp4"
    assert done["first_finished_at"] == "2026-10-19T09:30:00.000Z"
    assert done["finished_at"] != "2026-10-19T09:30:00.000Z"


def test_no_claim_while_a_job_runs(running_job, song, shoot):
    # created_at runs opposite to submitted_at, so only submitted_at makes queued[0] the oldest.
    queued = [
        add_job(
            shoot[0],
            song,
            status="queued",
            submitted_at=f"2026-10-19T09:0{i}:00.000Z",
            created_at=f"2026-10-19T08:0{3 - i}:00.000Z",
        )
        for i in (1, 2)
    ]
    started = row("jobs", running_job)["started_at"]

    assert race(worker_interface.claim_next_job, 4) == [None] * 4

    assert row("jobs", running_job)["started_at"] == started
    assert all(row("jobs", j)["status"] == "queued" for j in queued)

    passed_shot(running_job, 1, shoot[1][0])
    worker_interface.finish_job(running_job, "ready", video=VIDEO)
    assert worker_interface.claim_next_job().id == queued[0]


def test_each_run_gets_its_own_budget(song, shoot, clock):
    job = add_job(shoot[0], song, status="queued", submitted_at="2026-10-19T09:00:00.000Z")
    worker_interface.claim_next_job()
    assert row("jobs", job)["deadline_at"] == "2026-10-19T10:30:00.000Z"
    worker_interface.stop_job(job, "out_of_credit")

    requeue(job)
    clock.now = datetime(2026, 10, 19, 11, 0, 0, tzinfo=UTC)
    worker_interface.claim_next_job()

    again = row("jobs", job)
    assert again["started_at"] == "2026-10-19T11:00:00.000Z"
    assert again["deadline_at"] == "2026-10-19T11:30:00.000Z"
    assert (again["finished_at"], again["stop_reason"]) == (None, None)


def test_stop_and_finish_on_a_stopped_job_are_refused(running_job):
    worker_interface.stop_job(running_job, "out_of_credit")
    with pytest.raises(JobNotRunning):
        worker_interface.stop_job(running_job, "out_of_credit")
    with pytest.raises(JobNotRunning):
        worker_interface.finish_job(running_job, "ready", video=VIDEO)


def test_unknown_job_is_not_found(song):
    with pytest.raises(JobNotFound):
        worker_interface.stop_job("nope", "out_of_credit")
    with pytest.raises(JobNotFound):
        worker_interface.finish_job("nope", "ready", video=VIDEO)


def test_stop_with_an_unknown_reason_is_refused(running_job):
    with pytest.raises(ValueError):
        worker_interface.stop_job(running_job, "bored")
    assert row("jobs", running_job)["status"] == "running"


def test_interface_exposes_shot_writes():
    for name in (
        "set_shot_state",
        "set_shot_photo",
        "start_attempt",
        "finish_attempt",
        "set_shot_result",
    ):
        assert getattr(worker_interface, name) is getattr(shot_writes, name)


def test_stopped_job_total_includes_calls_that_finish_after_the_stop(running_job):
    from app.jobs import reading

    add_provider_call(running_job, 0.30)
    worker_interface.stop_job(running_job, "out_of_credit")
    add_provider_call(running_job, 0.50)  # a sibling shot's clip finishing after the stop

    assert reading.load_job(running_job).total_cost_usd == pytest.approx(0.80)


def test_run_context_offers_a_paid_recovered_clip_until_an_attempt_uses_it(running_job, shoot):
    shot = add_shot(running_job, 1, shoot[1][0], status="pending")
    attempt = add_attempt(shot, 1, status="error", error="worker_restarted")
    with session_scope() as session:
        session.execute(
            text(
                "insert into provider_calls (id,kind,model,job_id,job_shot_id,attempt_id,status,"
                "cost_usd,started_at) values ('call1','generate_clip','google/veo-3.1',:j,:s,:a,"
                "'ok',0.8,'2026-10-19T09:00:00.000Z')"
            ),
            {"j": running_job, "s": shot, "a": attempt},
        )

    offered = worker_interface.run_context(shot).recovered
    assert offered == worker_interface.RecoveredClip(
        "clips/recovered/call1.mp4", "google/veo-3.1", 3
    )

    used = add_attempt(shot, 2, round=1, status="passed")
    with session_scope() as session:
        session.execute(
            text("update attempts set clip_key='clips/recovered/call1.mp4' where id=:a"),
            {"a": used},
        )
    assert worker_interface.run_context(shot).recovered is None
