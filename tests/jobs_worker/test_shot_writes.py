import threading

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import shot_writes
from app.jobs.errors import AttemptLimitReached, JobNotRunning
from app.providers.errors import ProviderError
from app.shared.types import ClipCheck
from tests.support.worker_rows import add_attempt, add_job, add_shot, row, rows

NOTES = "a person appears in the mirror"


def check(passed=False, notes=NOTES, ai=0.8):
    return ClipCheck(
        ai_score=ai,
        match_score=0.9,
        people_count=1,
        added_objects=["person"],
        removed_objects=[],
        changed_objects=[],
        passed=passed,
        notes=notes,
    )


def attempt_count(shot):
    return rows("select count(*) n from attempts where job_shot_id = :s", s=shot)[0]["n"]


def test_fifth_attempt_is_refused(running_job):
    shot = add_shot(running_job, 1, status="generating")
    for n in range(1, 5):
        add_attempt(shot, n)
    with pytest.raises(AttemptLimitReached):
        shot_writes.start_attempt(shot, "p", "google/veo-3.1", 4.0)
    assert attempt_count(shot) == 4


def test_failed_shot_has_reason_and_last_notes(running_job):
    shot = add_shot(running_job, 1, status="checking")
    for n, notes in enumerate(["n1", "n2", "n3", NOTES], start=1):
        add_attempt(shot, n, check_notes=notes)
    shot_writes.set_shot_result(shot, "failed", "flagged_every_attempt")
    r = row("job_shots", shot)
    assert (r["status"], r["failure_reason"], r["status_detail"]) == (
        "failed",
        "flagged_every_attempt",
        NOTES,
    )


def test_crop_only_photo_is_recorded(running_job):
    shot = add_shot(running_job, 1, status="editing")
    shot_writes.set_shot_photo(shot, "jobs/J/shots/1/crop.jpg", None, "crop_only", "window changed")
    r = row("job_shots", shot)
    assert r["cropped_key"] == "jobs/J/shots/1/crop.jpg"
    assert r["edited_key"] is None
    assert (r["edit_status"], r["edit_note"], r["status"]) == (
        "crop_only",
        "window changed",
        "editing",
    )


def test_attempt_result_is_recorded(running_job):
    shot = add_shot(running_job, 1, status="checking")
    attempt = shot_writes.start_attempt(shot, "p", "google/veo-3.1", 4.0)
    shot_writes.finish_attempt(
        attempt, "flagged", clip_key="jobs/J/shots/1/r0/a1.mp4", check=check(), cost_usd=0.40
    )
    a = row("attempts", attempt)
    assert a["status"] == "flagged"
    assert a["check_ai_score"] == 0.8
    assert a["check_match_score"] == 0.9
    assert a["check_notes"] == NOTES
    assert a["cost_usd"] == pytest.approx(0.40)
    assert a["clip_key"] == "jobs/J/shots/1/r0/a1.mp4"
    assert a["finished_at"] is not None
    assert row("job_shots", shot)["status_detail"] == f"Attempt 1 of 4: flagged, {NOTES}"


def test_passed_attempt_detail(running_job):
    shot = add_shot(running_job, 1, status="checking")
    attempt = shot_writes.start_attempt(shot, "p", "m", 4.0)
    shot_writes.finish_attempt(attempt, "passed", check=check(True, "fine"))
    assert row("job_shots", shot)["status_detail"] == "Attempt 1 of 4: passed the check"


def test_provider_error_reaches_the_shot_at_once(running_job):
    shot = add_shot(running_job, 1, status="generating")
    attempt = shot_writes.start_attempt(shot, "p", "m", 4.0)
    shot_writes.finish_attempt(attempt, "error", error=ProviderError("rate_limited", "429"))
    a, s = row("attempts", attempt), row("job_shots", shot)
    assert a["status"] == "error"
    assert a["error"].startswith("rate_limited")
    assert a["finished_at"] is not None
    assert "busy" in s["status_detail"]
    assert s["updated_at"] == a["finished_at"]


def test_other_provider_errors_name_the_kind(running_job):
    shot = add_shot(running_job, 1, status="generating")
    attempt = shot_writes.start_attempt(shot, "p", "m", 4.0)
    shot_writes.finish_attempt(attempt, "error", error=ProviderError("refused", "no"))
    assert row("job_shots", shot)["status_detail"] == "Attempt 1 of 4: provider error (refused)"


def test_failure_needs_a_known_reason(running_job):
    shot = add_shot(running_job, 1, status="checking")
    before = row("job_shots", shot)
    for reason in (None, "oops"):
        with pytest.raises(ValueError):
            shot_writes.set_shot_result(shot, "failed", reason)
    with pytest.raises(ValueError):
        shot_writes.set_shot_state(shot, "failed", "x")
    assert row("job_shots", shot) == before


def test_failure_sentences_and_provider_error(running_job):
    a = add_shot(running_job, 1, status="generating")
    attempt = shot_writes.start_attempt(a, "p", "m", 4.0)
    shot_writes.finish_attempt(attempt, "error", error=ProviderError("failed", "boom"))
    shot_writes.set_shot_result(a, "failed", "provider_error")
    assert row("job_shots", a)["status_detail"] == "failed: boom"
    b = add_shot(running_job, 2, status="pending")
    shot_writes.set_shot_result(b, "failed", "no_photo")
    assert row("job_shots", b)["status_detail"] == "No photo of this room."


def test_pass_needs_checking_and_a_passed_attempt(running_job):
    shot = add_shot(running_job, 1, status="checking")
    bad = add_attempt(shot, 1, status="flagged")
    good = add_attempt(shot, 2, status="passed")
    with pytest.raises(ValueError):
        shot_writes.set_shot_result(shot, "passed", final_attempt_id=bad)
    with pytest.raises(ValueError):
        shot_writes.set_shot_result(shot, "passed")
    shot_writes.set_shot_result(shot, "passed", final_attempt_id=good)
    r = row("job_shots", shot)
    assert (r["status"], r["final_attempt_id"], r["model_used"]) == (
        "passed",
        good,
        "google/veo-3.1",
    )
    assert r["failure_reason"] is None
    other = add_shot(running_job, 2, status="generating")
    a = add_attempt(other, 1, status="passed")
    with pytest.raises(ValueError):
        shot_writes.set_shot_result(other, "passed", final_attempt_id=a)
    with pytest.raises(ValueError):
        shot_writes.set_shot_result(other, "skipped")


def test_shot_states_move_only_along_the_rules(running_job):
    shot = add_shot(running_job, 1, status="pending")
    with pytest.raises(ValueError):
        shot_writes.set_shot_state(shot, "generating", "x")
    with pytest.raises(ValueError):
        shot_writes.set_shot_state(shot, "passed", "x")
    for status in ("editing", "editing", "generating", "checking", "generating", "checking"):
        shot_writes.set_shot_state(shot, status, f"to {status}")
        assert row("job_shots", shot)["status"] == status
    assert row("job_shots", shot)["status_detail"] == "to checking"
    with pytest.raises(ValueError):
        shot_writes.set_shot_state(shot, "editing", "x")


def test_unknown_shot_is_a_lookup_error(running_job):
    with pytest.raises(LookupError):
        shot_writes.set_shot_state("nope", "editing", "x")


def test_photo_rules(running_job):
    shot = add_shot(running_job, 1, status="generating")
    with pytest.raises(ValueError):
        shot_writes.set_shot_photo(shot, "c", "e", "edited", None)
    editing = add_shot(running_job, 2, status="editing")
    with pytest.raises(ValueError):
        shot_writes.set_shot_photo(editing, "c", "e", "weird", None)


def test_start_attempt_needs_an_in_flight_shot(running_job):
    shot = add_shot(running_job, 1, status="pending")
    with pytest.raises(ValueError):
        shot_writes.start_attempt(shot, "p", "m", 4.0)


@pytest.fixture(params=["state", "photo", "start", "finish", "result"])
def write_after_stop(request, running_job):
    shot = add_shot(running_job, 1, status="editing" if request.param == "photo" else "generating")
    running_attempt = add_attempt(shot, 1, status="running")
    calls = {
        "state": lambda: shot_writes.set_shot_state(shot, "checking", "x"),
        "photo": lambda: shot_writes.set_shot_photo(shot, "c", None, "crop_only", "n"),
        "start": lambda: shot_writes.start_attempt(shot, "p", "m", 4.0),
        "finish": lambda: shot_writes.finish_attempt(running_attempt, "flagged", check=check()),
        "result": lambda: shot_writes.set_shot_result(shot, "failed", "refused"),
    }
    with session_scope() as s:
        s.execute(
            text("update jobs set status='stopped', stop_reason='out_of_credit' where id=:i"),
            {"i": running_job},
        )
    return shot, running_attempt, calls[request.param]


def test_writes_after_stop_are_refused(write_after_stop):
    shot, attempt, call = write_after_stop
    before = (row("job_shots", shot), row("attempts", attempt), attempt_count(shot))
    with pytest.raises(JobNotRunning):
        call()
    assert (row("job_shots", shot), row("attempts", attempt), attempt_count(shot)) == before


def test_four_attempts_per_round_under_threads(running_job):
    shot = add_shot(running_job, 1, status="generating")
    barrier = threading.Barrier(6)
    results = []

    def go():
        barrier.wait()
        try:
            results.append(shot_writes.start_attempt(shot, "p", "m", 4.0))
        except AttemptLimitReached:
            results.append(None)

    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sum(r is not None for r in results) == 4
    assert len(results) == 6
    nos = sorted(r["attempt_no"] for r in rows("select attempt_no from attempts"))
    assert nos == [1, 2, 3, 4]


def test_new_round_starts_at_attempt_one(running_job):
    shot = add_shot(running_job, 1, status="generating", round=1)
    for n in range(1, 5):
        add_attempt(shot, n, round=0)
    attempt = shot_writes.start_attempt(shot, "p", "m", 4.0)
    a = row("attempts", attempt)
    assert (a["round"], a["attempt_no"]) == (1, 1)


def test_many_shots_in_parallel_all_succeed(song, shoot, clock):
    job = add_job(shoot[0], song, status="running")
    shots = [add_shot(job, i, status="generating") for i in range(1, 9)]
    barrier = threading.Barrier(8)
    errors = []

    def go(shot):
        barrier.wait()
        try:
            for _ in range(4):
                shot_writes.start_attempt(shot, "p", "m", 4.0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(s,)) for s in shots]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    assert rows("select count(*) n from attempts")[0]["n"] == 32
