import json

from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import planning
from app.jobs.plan_rules import MOVEMENTS
from app.library import stubs as library_stubs
from tests.support.jobs_rows import add_draft_job, add_ready_shoot, planned_shot

SONG_ID = library_stubs.STUB_SONG.id


def _seed(n=6, **job_args):
    photoshoot_id, photo_ids = add_ready_shoot(n)
    job_id = add_draft_job(photoshoot_id, SONG_ID, **job_args)
    return job_id, photo_ids


def _plan(photo_ids):
    return [planned_shot(i, pid) for i, pid in enumerate(photo_ids, start=1)]


def _get(client, job_id):
    return client.get(f"/api/jobs/{job_id}")


def test_plan_arrives_with_six_ordered_shots(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    scripted_planner.queue(_plan(photo_ids))

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "ready"
    assert [s["position"] for s in body["shots"]] == [1, 2, 3, 4, 5, 6]
    assert [s["planNote"] for s in body["shots"]] == [f"Shot {i} note." for i in range(1, 7)]
    assert body["status"] == "draft"


def test_skipped_pool_shot_has_no_photo_and_notes_name_the_pool(
    client, stub_presets, scripted_planner
):
    job_id, photo_ids = _seed(5)
    shots = _plan(photo_ids)
    shots.append(planned_shot(6, None, room="other", planNote="No pool photo, skipped."))
    scripted_planner.queue(shots, notes="The text asks for a pool; no pool photo.")

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "ready"
    assert body["shots"][5]["photoId"] is None
    assert "pool" in body["planNotes"]


def test_invalid_plan_is_asked_again_once(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    bad = _plan(photo_ids)
    bad[1] = planned_shot(2, photo_ids[1], movementName="spin_around")
    good = _plan(photo_ids)
    good[2] = planned_shot(3, photo_ids[2], movementName="crane_up", planNote="Second plan.")
    scripted_planner.queue(bad)
    scripted_planner.queue(good)

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "ready"
    assert body["shots"][2]["movementName"] == "crane_up"
    assert len(scripted_planner.calls) == 2
    second_text = scripted_planner.calls[1]["style_text"]
    assert second_text.startswith("Slow Dolly In through each room")
    assert "Shot 2" in second_text and "unknown movement" in second_text


def test_two_bad_plans_fail_with_reason(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    bad = _plan(photo_ids)
    bad[1] = planned_shot(2, photo_ids[1], movementName="spin_around")
    scripted_planner.queue(bad)
    scripted_planner.queue(bad)

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "failed"
    assert "unknown movement" in body["planNotes"]
    assert body["shots"] == []
    assert len(scripted_planner.calls) == 2
    with session_scope() as session:
        count = session.scalar(
            text("select count(*) from job_shots where job_id = :j"), {"j": job_id}
        )
    assert count == 0


def test_nan_length_counts_as_an_invalid_plan(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    nan_plan = _plan(photo_ids)
    nan_plan[0] = planned_shot(1, photo_ids[0], lengthS=float("nan"))
    scripted_planner.queue(nan_plan)
    scripted_planner.queue(nan_plan)

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "failed"
    assert "finite" in body["planNotes"]


def test_crash_in_the_planner_fails_the_job(client, stub_presets, scripted_planner):
    job_id, _ = _seed()
    scripted_planner.answers.append(RuntimeError("planner exploded"))

    planning.plan_job(job_id)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "failed"
    assert "planner exploded" in body["planNotes"]


def test_ob1_plan_records_style_photo_prompts_and_model(client, stub_presets, scripted_planner):
    style_id = library_stubs.GOLDEN_HOUR_ID
    job_id, photo_ids = _seed(style_id=style_id, style_text="Golden light everywhere")
    shots = _plan(photo_ids)
    shots[0] = planned_shot(1, photo_ids[0], photoEditPrompts=["Remove the car."])
    shots[3] = planned_shot(
        4, photo_ids[3], model="bytedance/seedance-2.0", movementName="crane_up",
        movementPrompt=MOVEMENTS["crane_up"],
    )  # fmt: skip
    scripted_planner.queue(shots)

    planning.plan_job(job_id)

    with session_scope() as session:
        job = session.execute(
            text("select style_id, style_text from jobs where id = :j"), {"j": job_id}
        ).one()
        rows = session.execute(
            text(
                "select photo_id, photo_edit_prompts, movement_prompt, model from job_shots"
                " where job_id = :j order by position"
            ),
            {"j": job_id},
        ).all()
    assert (job.style_id, job.style_text) == (style_id, "Golden light everywhere")
    assert len(rows) == 6
    for row, shot in zip(rows, shots, strict=True):
        assert row.photo_id == shot["photoId"]
        assert json.loads(row.photo_edit_prompts) == shot["photoEditPrompts"]
        assert row.movement_prompt == shot["movementPrompt"]
        assert row.model == shot["model"]
    assert _get(client, job_id).json()["job"]["styleName"] == "Golden hour"


def test_stale_plan_is_dropped(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    scripted_planner.queue(_plan(photo_ids))
    old = planning._bump(job_id)
    planning._bump(job_id)  # a re-plan started after this run

    planning.plan_job(job_id, old)

    body = _get(client, job_id).json()["job"]
    assert body["planStatus"] == "planning"
    assert body["shots"] == []


def test_get_unknown_job_is_404(client):
    response = client.get("/api/jobs/nope")

    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"


def test_start_plans_in_a_background_thread(client, stub_presets, scripted_planner):
    job_id, photo_ids = _seed()
    scripted_planner.queue(_plan(photo_ids))

    planning.start(job_id)
    planning.wait_idle()

    assert _get(client, job_id).json()["job"]["planStatus"] == "ready"
