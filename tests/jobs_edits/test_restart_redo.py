import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import worker_interface as worker
from app.jobs.errors import AttemptLimitReached
from tests.support.queue_rows import add_attempt, add_shot, job_row, shot_rows

PLAN_FIELDS = (
    "position", "room", "photo_id", "photo_edit_prompts", "movement_name", "movement_prompt",
    "speed", "model", "length_s", "transition", "transition_s", "plan_note", "removed",
)  # fmt: skip


def test_restart_keeps_passed_shots(bucket, client, make_job):
    job_id = make_job(status="stopped", passed=3, failed=2, stop_reason="out_of_credit")
    before = shot_rows(job_id)

    response = client.post(f"/api/jobs/{job_id}/restart")

    assert response.status_code == 202
    assert response.json()["job"]["status"] == "queued"
    assert job_row(job_id)["status"] == "queued"
    after = shot_rows(job_id)
    for position in (4, 5):
        assert after[position]["status"] == "pending"
        assert after[position]["round"] == 1
        assert after[position]["failure_reason"] is None
    for position in (1, 2, 3):
        assert after[position] == before[position]


def test_only_a_stopped_job_restarts(bucket, client, make_job):
    job_id = make_job(status="ready")
    before = shot_rows(job_id)

    response = client.post(f"/api/jobs/{job_id}/restart")

    assert (response.status_code, response.json()["error"]) == (409, "not_stopped")
    assert job_row(job_id)["status"] == "ready"
    assert shot_rows(job_id) == before


def test_redo_one_shot(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    before = shot_rows(job_id)

    response = client.post(f"/api/jobs/{job_id}/shots/4/redo")

    assert response.status_code == 202
    job = response.json()["job"]
    assert job["status"] == "queued"
    assert job_row(job_id)["status"] == "queued"
    after = shot_rows(job_id)
    assert after[4]["status"] == "pending"
    assert after[4]["round"] == 1
    assert after[4]["final_attempt_id"] is None
    assert job["shots"][3]["clipUrl"] is None
    for position in (1, 2, 3, 5, 6):
        assert after[position] == before[position]
        assert job["shots"][position - 1]["clipUrl"] is not None


def test_no_redo_while_busy(bucket, client, make_job):
    queued = make_job(status="queued")
    running = make_job(status="running")
    before = shot_rows(queued)

    answers = [client.post(f"/api/jobs/{j}/shots/4/redo") for j in (queued, running)]

    assert [(a.status_code, a.json()["error"]) for a in answers] == [(409, "job_busy")] * 2
    assert shot_rows(queued) == before


def test_redo_errors(bucket, client, make_job, shoot):
    draft = make_job(status="draft")
    stopped = make_job(status="stopped", stop_reason="out_of_credit")
    ready = make_job(status="ready", passed=2)
    no_photo = add_shot(ready, 3, None, status="skipped", failure_reason="no_photo")
    removed = add_shot(ready, 4, shoot[1][3], status="passed", removed=1)

    with session_scope() as session:
        session.execute(
            text("update job_shots set edited_at = :t where id = :i"),
            {"t": job_row(ready)["submitted_at"], "i": removed},
        )

    answers = [
        client.post(url)
        for url in (
            "/api/jobs/nope/shots/1/redo",
            f"/api/jobs/{ready}/shots/9/redo",
            f"/api/jobs/{draft}/shots/1/redo",
            f"/api/jobs/{stopped}/shots/1/redo",
            f"/api/jobs/{ready}/shots/3/redo",
            f"/api/jobs/{ready}/shots/4/redo",
        )
    ]

    assert [(a.status_code, a.json()["error"]) for a in answers] == [
        (404, "job_not_found"),
        (404, "shot_not_found"),
        (409, "not_finished"),
        (409, "not_finished"),
        (409, "no_photo"),
        (409, "shot_removed"),
    ]
    rows = shot_rows(ready)
    assert (rows[3]["id"], rows[3]["status"]) == (no_photo, "skipped")
    assert (rows[4]["id"], rows[4]["status"], rows[4]["round"]) == (removed, "passed", 0)
    assert job_row(ready)["status"] == "ready"


@pytest.mark.parametrize("action", ["restart", "shots/2/redo"])
def test_restart_gives_four_new_attempts(bucket, client, make_job, action):
    job_id = make_job(
        status="stopped" if action == "restart" else "ready_with_failures",
        passed=1,
        failed=1,
        stop_reason="out_of_credit" if action == "restart" else None,
    )
    shot_id = shot_rows(job_id)[2]["id"]
    for attempt_no in (1, 2, 3, 4):
        add_attempt(shot_id, attempt_no, "flagged")

    assert client.post(f"/api/jobs/{job_id}/{action}").status_code == 202
    worker.claim_next_job()
    worker.set_shot_state(shot_id, "editing", "Editing the photo")
    new_round = [worker.start_attempt(shot_id, "p", "google/veo-3.1", 4.0) for _ in range(4)]

    assert len(new_round) == 4
    with pytest.raises(AttemptLimitReached):
        worker.start_attempt(shot_id, "p", "google/veo-3.1", 4.0)


@pytest.mark.parametrize(
    ("status", "url"),
    [("stopped", "/api/jobs/{}/restart"), ("ready", "/api/jobs/{}/shots/2/redo")],
)
def test_restart_and_redo_never_change_plan_fields(bucket, client, make_job, status, url):
    job_id = make_job(status=status, passed=1, failed=2, stop_reason="out_of_credit")
    before = shot_rows(job_id)

    response = client.post(url.format(job_id))

    assert response.status_code == 202
    after = shot_rows(job_id)
    for position, row in before.items():
        assert {f: after[position][f] for f in PLAN_FIELDS} == {f: row[f] for f in PLAN_FIELDS}


@pytest.mark.parametrize(
    "body",
    [
        {"speed": "fast"},
        {"lengthS": 2.0},
        {"removed": True},
    ],
)
def test_redo_rejects_pending_edits_without_mutation(bucket, client, make_job, body):
    job_id = make_job()
    assert client.patch(f"/api/jobs/{job_id}/shots/2", json=body).status_code == 200
    before_job, before_shots = job_row(job_id), shot_rows(job_id)

    response = client.post(f"/api/jobs/{job_id}/shots/4/redo")

    assert (response.status_code, response.json()["error"]) == (409, "pending_edits")
    assert job_row(job_id) == before_job
    assert shot_rows(job_id) == before_shots
    print(
        {
            "redoStatus": response.status_code,
            "error": response.json()["error"],
            "jobAndShotsUnchanged": True,
        }
    )


def test_concurrent_claim_waits_for_job_write_transaction(bucket, make_job):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from sqlalchemy import text

    from app.db.base import session_scope

    job_id = make_job()
    entered = Event()

    def claim():
        entered.set()
        return worker.claim_next_job()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with session_scope() as session:
            session.execute(text("update jobs set status='queued' where id=:j"), {"j": job_id})
            future = pool.submit(claim)
            assert entered.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        claimed = future.result(timeout=5)

    assert claimed.id == job_id
    assert job_row(job_id)["status"] == "running"


def test_restart_preserves_history_and_excludes_ineligible_shots(bucket, client, make_job, shoot):
    job_id = make_job(status="stopped", passed=1, failed=1, stop_reason="out_of_credit")
    add_shot(job_id, 3, shoot[1][2], status="skipped")
    add_shot(job_id, 4, shoot[1][3], status="failed", removed=1, failure_reason="job_stopped")
    add_shot(job_id, 5, None, status="failed", failure_reason="job_stopped")
    before = shot_rows(job_id)
    attempt_id = add_attempt(before[2]["id"], 1, "error", "historical.mp4")
    with session_scope() as session:
        history = [dict(r) for r in session.execute(text("select * from attempts")).mappings()]

    response = client.post(f"/api/jobs/{job_id}/restart")

    assert response.status_code == 202
    assert job_row(job_id)["stop_reason"] is None
    after = shot_rows(job_id)
    for position in (1, 3, 5):
        assert after[position] == before[position]
    assert after[4]["status"] == "failed"
    assert after[4]["round"] == 0
    assert after[4]["final_attempt_id"] == before[4]["final_attempt_id"]
    assert response.json()["job"]["shots"][0]["clipUrl"] is not None
    with session_scope() as session:
        assert [
            dict(r) for r in session.execute(text("select * from attempts")).mappings()
        ] == history
    assert attempt_id in {row["id"] for row in history}
    claimed = worker.claim_next_job()
    assert [shot.position for shot in claimed.shots] == [2]
