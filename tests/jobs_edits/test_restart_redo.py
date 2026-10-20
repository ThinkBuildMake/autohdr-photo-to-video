import pytest

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


def test_restart_gives_four_new_attempts(bucket, client, make_job):
    job_id = make_job(status="stopped", passed=1, failed=1, stop_reason="out_of_credit")
    shot_id = shot_rows(job_id)[2]["id"]
    for attempt_no in (1, 2, 3, 4):
        add_attempt(shot_id, attempt_no, "flagged")

    client.post(f"/api/jobs/{job_id}/restart")
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
