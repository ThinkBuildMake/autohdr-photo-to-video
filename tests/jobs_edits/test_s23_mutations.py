"""Restart and redo transaction invariants through the Jobs API."""

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import worker_interface as worker
from tests.support.queue_rows import job_row, shot_rows


@pytest.mark.parametrize("action", ["restart", "shots/2/redo", "export"])
def test_requeue_clears_old_run_clock(bucket, client, make_job, action):
    job_id = make_job(
        status="stopped" if action == "restart" else "ready",
        passed=2,
        stop_reason="out_of_credit" if action == "restart" else None,
    )
    if action == "export":
        assert client.patch(f"/api/jobs/{job_id}/shots/1", json={"lengthS": 2}).status_code == 200
    with session_scope() as session:
        session.execute(
            text(
                "update jobs set started_at = :t, deadline_at = :t, first_finished_at = :t "
                "where id = :i"
            ),
            {"t": "2026-10-19T09:01:00.000Z", "i": job_id},
        )
    before = job_row(job_id)

    response = client.post(f"/api/jobs/{job_id}/{action}")

    assert response.status_code == 202
    queued = job_row(job_id)
    assert [queued[key] for key in ("started_at", "deadline_at", "finished_at")] == [None] * 3
    assert queued["first_submitted_at"] == before["first_submitted_at"]
    assert queued["first_finished_at"] == before["first_finished_at"]
    assert worker.claim_next_job().id == job_id
    claimed = job_row(job_id)
    assert claimed["started_at"] >= claimed["submitted_at"]
    assert claimed["deadline_at"] > claimed["started_at"]


@pytest.mark.parametrize("change", ["new_clip", "recut_only", "removal", "put_back"])
@pytest.mark.parametrize("position", [1, 2])
def test_redo_rejects_pending_edits_without_mutation(bucket, client, make_job, change, position):
    job_id = make_job(passed=2)
    url = f"/api/jobs/{job_id}/shots/1"
    if change == "put_back":
        # Shot 1 was omitted from the delivered video, then restored in the editor.
        with session_scope() as session:
            session.execute(
                text(
                    "update job_shots set removed = 1, edited_at = :t where job_id = :i "
                    "and position = 1"
                ),
                {"t": job_row(job_id)["submitted_at"], "i": job_id},
            )
    body = {
        "new_clip": {"speed": "fast"},
        "recut_only": {"lengthS": 2},
        "removal": {"removed": True},
        "put_back": {"removed": False},
    }[change]
    assert client.patch(url, json=body).status_code == 200
    before_job, before_shots = job_row(job_id), shot_rows(job_id)

    response = client.post(f"/api/jobs/{job_id}/shots/{position}/redo")

    assert (response.status_code, response.json()["error"]) == (409, "pending_edits")
    assert response.json()["message"] == "Export your saved edits before redoing a shot."
    assert job_row(job_id) == before_job
    assert shot_rows(job_id) == before_shots


@pytest.mark.parametrize("action", ["restart", "shots/2/redo"])
def test_duplicate_actions_queue_exactly_one_round(bucket, client, make_job, action):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    job_id = make_job(
        status="stopped" if action == "restart" else "ready",
        passed=1,
        failed=1,
        stop_reason="out_of_credit" if action == "restart" else None,
    )
    barrier = Barrier(2)

    def request():
        barrier.wait(timeout=5)
        return client.post(f"/api/jobs/{job_id}/{action}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(), range(2)))

    assert sorted(r.status_code for r in responses) == [202, 409]
    rejected = next(r for r in responses if r.status_code == 409)
    assert rejected.json()["error"] == ("not_stopped" if action == "restart" else "job_busy")
    rows = shot_rows(job_id)
    assert (rows[1]["round"], rows[2]["round"]) == (0, 1)
    assert job_row(job_id)["status"] == "queued"
