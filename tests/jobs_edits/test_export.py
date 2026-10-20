import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import reading
from app.jobs import worker_interface as worker
from tests.support.queue_rows import add_shot, job_row, shot_rows

PLAN_FIELDS = (
    "position", "room", "photo_id", "photo_edit_prompts", "movement_name", "movement_prompt",
    "speed", "model", "length_s", "transition", "transition_s", "plan_note", "removed",
)  # fmt: skip


def _export(client, job_id):
    return client.post(f"/api/jobs/{job_id}/export")


def test_reexport_makes_only_what_changed(bucket, client, make_job, shoot):
    job_id = make_job(status="ready", passed=6)
    client.patch(f"/api/jobs/{job_id}/shots/2", json={"photoId": shoot[1][7]})
    client.patch(f"/api/jobs/{job_id}/shots/1", json={"lengthS": 3.5})
    before = shot_rows(job_id)

    response = _export(client, job_id)

    assert response.status_code == 202
    assert response.json()["job"]["status"] == "queued"
    assert job_row(job_id)["status"] == "queued"
    after = shot_rows(job_id)
    assert [p for p, row in after.items() if row["status"] == "pending"] == [2]
    assert (after[2]["round"], after[2]["needs_new_clip"]) == (1, 0)
    assert after[1]["final_attempt_id"] == before[1]["final_attempt_id"]
    assert after[1]["length_s"] == 3.5
    assert [s["pendingChange"] for s in response.json()["job"]["shots"]] == ["none"] * 6


def test_nothing_to_export(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _export(client, job_id)

    assert (response.status_code, response.json()["error"]) == (409, "nothing_to_export")
    assert job_row(job_id)["status"] == "ready"


def test_untouched_shots_never_change(bucket, client, make_job, shoot):
    job_id = make_job(status="ready", passed=6)
    client.patch(f"/api/jobs/{job_id}/shots/2", json={"photoId": shoot[1][7]})
    before = shot_rows(job_id)

    response = _export(client, job_id)

    assert response.status_code == 202
    after = shot_rows(job_id)
    for position in (1, 3, 4, 5, 6):
        assert after[position]["final_attempt_id"] is not None
        assert after[position] == before[position]
    assert after[2]["final_attempt_id"] is None


def test_reexport_starts_a_new_run_clock(bucket, client, make_job, monkeypatch):
    job_id = make_job(status="ready", passed=6)
    monkeypatch.setattr(reading, "now_utc", lambda: "2026-10-19T13:00:00.000Z")
    client.patch(f"/api/jobs/{job_id}/shots/2", json={"speed": "fast"})
    monkeypatch.setattr(reading, "now_utc", lambda: "2026-10-19T14:00:00.000Z")

    response = _export(client, job_id)

    assert response.status_code == 202
    assert response.json()["job"]["submittedAt"] == "2026-10-19T14:00:00.000Z"
    row = job_row(job_id)
    assert row["submitted_at"] == "2026-10-19T14:00:00.000Z"
    assert row["first_submitted_at"] == "2026-10-19T09:00:00.000Z"


def test_recut_only_export_makes_no_shot(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    client.patch(f"/api/jobs/{job_id}/shots/3", json={"speed": "fast"})
    edit = client.patch(f"/api/jobs/{job_id}/shots/3", json={"removed": True})

    response = _export(client, job_id)

    assert edit.json()["exportPlan"] == {"newClips": 0, "recutOnly": 0, "removed": 1}

    assert response.status_code == 202
    assert job_row(job_id)["status"] == "queued"
    assert all(row["status"] == "passed" for row in shot_rows(job_id).values())


def test_export_errors(bucket, client, make_job):
    queued = make_job(status="queued")
    draft = make_job(status="draft")
    stopped = make_job(status="stopped", stop_reason="out_of_credit")

    answers = [_export(client, job_id) for job_id in ("nope", queued, draft, stopped)]

    assert [(a.status_code, a.json()["error"]) for a in answers] == [
        (404, "job_not_found"),
        (409, "job_busy"),
        (409, "not_finished"),
        (409, "not_finished"),
    ]


def test_edit_and_export_change_only_the_edited_shot(bucket, client, make_job):
    job_id = make_job(status="ready", passed=3, failed=1)
    before = shot_rows(job_id)

    client.patch(f"/api/jobs/{job_id}/shots/2", json={"speed": "fast"})
    _export(client, job_id)

    after = shot_rows(job_id)
    for position in (1, 3, 4):
        assert after[position] == before[position]
    changed = {f for f in PLAN_FIELDS if after[2][f] != before[2][f]}
    assert changed == {"speed", "plan_note"}


@pytest.mark.parametrize("body", [{"lengthS": 2.0}, {"movementName": "crane_up"}])
def test_photoless_shot_is_never_made_on_export(bucket, client, make_job, body):
    job_id = make_job(status="ready_with_failures", passed=2)
    add_shot(job_id, 3, None, status="skipped", failure_reason="no_photo")

    edit = client.patch(f"/api/jobs/{job_id}/shots/3", json=body)
    _export(client, job_id)
    claimed = worker.claim_next_job()

    assert edit.json()["shot"]["pendingChange"] != "new_clip"
    row = shot_rows(job_id)[3]
    assert (row["status"], row["failure_reason"], row["needs_new_clip"]) == (
        "skipped",
        "no_photo",
        0,
    )
    assert [s.position for s in claimed.shots] == []


def test_export_never_requeues_a_photoless_shot(bucket, client, make_job):
    job_id = make_job(status="ready_with_failures", passed=2)
    shot_id = add_shot(job_id, 3, None, status="skipped", failure_reason="no_photo")
    with session_scope() as session:
        session.execute(
            text("update job_shots set needs_new_clip = 1 where id = :i"), {"i": shot_id}
        )
    client.patch(f"/api/jobs/{job_id}/shots/1", json={"speed": "fast"})

    response = _export(client, job_id)

    assert response.status_code == 202
    rows = shot_rows(job_id)
    assert rows[1]["status"] == "pending"
    assert (rows[3]["status"], rows[3]["round"]) == ("skipped", 0)
