import pytest
from sqlalchemy import text

from app.db.base import session_scope
from tests.support.queue_rows import job_row, shot_rows


def _patch(client, job_id, position, body):
    return client.patch(f"/api/jobs/{job_id}/shots/{position}", json=body)


def test_swap_a_room_needs_a_new_clip(bucket, client, make_job, shoot):
    job_id = make_job(status="ready", passed=6)
    other_photo = shoot[1][7]

    response = _patch(client, job_id, 2, {"photoId": other_photo})

    assert response.status_code == 200
    assert response.json()["shot"]["pendingChange"] == "new_clip"
    row = shot_rows(job_id)[2]
    assert (row["photo_id"], row["needs_new_clip"]) == (other_photo, 1)


def test_change_movement_needs_a_new_clip(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _patch(client, job_id, 3, {"movementName": "slider_truck_left_to_right"})

    assert response.status_code == 200
    shot = response.json()["shot"]
    assert shot["pendingChange"] == "new_clip"
    assert shot["movementName"] == "slider_truck_left_to_right"
    assert shot_rows(job_id)[3]["needs_new_clip"] == 1


@pytest.mark.parametrize(
    "body", [{"lengthS": 3.5}, {"transition": "crossfade", "transitionS": 0.5}]
)
def test_length_or_transition_only_recuts(bucket, client, make_job, body):
    job_id = make_job(status="ready", passed=6)
    before = shot_rows(job_id)[1]

    response = _patch(client, job_id, 1, body)

    assert response.status_code == 200
    shot = response.json()["shot"]
    assert shot["pendingChange"] == "recut_only"
    assert shot["clipUrl"] is not None
    assert response.json()["exportPlan"] == {"newClips": 0, "recutOnly": 1, "removed": 0}
    after = shot_rows(job_id)[1]
    assert after["needs_new_clip"] == 0
    assert after["final_attempt_id"] == before["final_attempt_id"]


def test_length_longer_than_the_clip_needs_a_new_clip(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _patch(client, job_id, 1, {"lengthS": 5.0})

    assert response.status_code == 200
    assert response.json()["shot"]["pendingChange"] == "new_clip"


def test_remove_a_room(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _patch(client, job_id, 5, {"removed": True})

    assert response.status_code == 200
    assert response.json()["shot"]["removed"] is True
    assert response.json()["exportPlan"] == {"newClips": 0, "recutOnly": 0, "removed": 1}
    assert shot_rows(job_id)[5]["removed"] == 1


def test_put_a_room_back(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    with session_scope() as session:
        session.execute(
            text("update job_shots set removed = 1 where job_id = :j and position = 5"),
            {"j": job_id},
        )
    before = shot_rows(job_id)[5]

    response = _patch(client, job_id, 5, {"removed": False})

    assert response.status_code == 200
    assert response.json()["shot"]["removed"] is False
    assert response.json()["exportPlan"]["removed"] == 0
    after = shot_rows(job_id)[5]
    assert after["removed"] == 0
    kept = [k for k in before if k not in ("removed", "edited_at")]
    assert {k: after[k] for k in kept} == {k: before[k] for k in kept}


def test_bad_edit_names_the_photo(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    before = shot_rows(job_id)[2]
    stranger = "99999999-9999-4999-8999-999999999999"

    response = _patch(client, job_id, 2, {"photoId": stranger})

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_edit"
    assert stranger in response.json()["message"]
    assert shot_rows(job_id)[2] == before


def test_speed_change_needs_a_new_clip(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _patch(client, job_id, 6, {"speed": "fast"})

    assert response.status_code == 200
    assert response.json()["shot"]["pendingChange"] == "new_clip"
    assert shot_rows(job_id)[6]["speed"] == "fast"


def test_edit_errors(bucket, client, make_job):
    queued = make_job(status="queued")
    stopped = make_job(status="stopped", stop_reason="out_of_credit")
    ready = make_job(status="ready", passed=2)

    answers = [
        _patch(client, job_id, position, body)
        for job_id, position, body in (
            ("nope", 1, {"speed": "fast"}),
            (ready, 9, {"speed": "fast"}),
            (queued, 1, {"speed": "fast"}),
            (stopped, 1, {"speed": "fast"}),
            (ready, 1, {"movementName": "moonwalk"}),
            (ready, 2, {"lengthS": 9.0}),
        )
    ]

    assert [(a.status_code, a.json()["error"]) for a in answers] == [
        (404, "job_not_found"),
        (404, "shot_not_found"),
        (409, "job_busy"),
        (409, "not_finished"),
        (400, "invalid_edit"),
        (400, "invalid_edit"),
    ]
    assert "moonwalk" in answers[4].json()["message"]
    assert "Shot 2:" in answers[5].json()["message"]
    assert job_row(ready)["status"] == "ready"


def test_edit_that_changes_nothing_is_not_an_edit(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)

    response = _patch(client, job_id, 1, {"lengthS": 3.0, "removed": False})
    export = client.post(f"/api/jobs/{job_id}/export")

    assert response.json()["shot"]["pendingChange"] == "none"
    assert shot_rows(job_id)[1]["edited_at"] is None
    assert (export.status_code, export.json()["error"]) == (409, "nothing_to_export")


def test_removed_shot_shows_no_pending_change(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    _patch(client, job_id, 3, {"speed": "fast"})

    response = _patch(client, job_id, 3, {"removed": True})

    assert response.json()["shot"]["pendingChange"] == "none"
    assert response.json()["exportPlan"] == {"newClips": 0, "recutOnly": 0, "removed": 1}


def _finish_run(job_id):
    with session_scope() as session:
        session.execute(text("update jobs set status = 'ready' where id = :j"), {"j": job_id})


def test_remove_then_put_back_changes_nothing(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    _patch(client, job_id, 5, {"removed": True})

    response = _patch(client, job_id, 5, {"removed": False})

    assert response.json()["shot"]["pendingChange"] == "none"
    assert response.json()["exportPlan"] == {"newClips": 0, "recutOnly": 0, "removed": 0}
    export = client.post(f"/api/jobs/{job_id}/export")
    assert (export.status_code, export.json()["error"]) == (409, "nothing_to_export")


def test_removing_a_shot_of_the_last_video_is_exported(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    _patch(client, job_id, 5, {"removed": True})

    export = client.post(f"/api/jobs/{job_id}/export")

    assert export.status_code == 202


def test_putting_back_a_shot_left_out_of_the_last_video_recuts(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    _patch(client, job_id, 5, {"removed": True})
    assert client.post(f"/api/jobs/{job_id}/export").status_code == 202
    _finish_run(job_id)

    response = _patch(client, job_id, 5, {"removed": False})

    assert response.json()["shot"]["pendingChange"] == "recut_only"
    assert client.post(f"/api/jobs/{job_id}/export").status_code == 202


def test_put_back_after_another_change_recuts(bucket, client, make_job):
    job_id = make_job(status="ready", passed=6)
    _patch(client, job_id, 5, {"removed": True})
    _patch(client, job_id, 5, {"lengthS": 3.5})

    response = _patch(client, job_id, 5, {"removed": False})

    assert response.json()["shot"]["pendingChange"] == "recut_only"
