import threading

from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import planning, store
from app.library import stubs as library_stubs
from app.shared.types import PlannedShot
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE
from tests.support.jobs_rows import add_draft_job, add_ready_shoot, planned_shot

SONG_ID = library_stubs.STUB_SONG.id
GOLDEN = library_stubs.GOLDEN_HOUR_ID
GOLDEN_TEXT = library_stubs.STUB_STYLES[0].style_text
TEXT = "Slow Dolly In through each room"


def _plan(photo_ids):
    return [planned_shot(i, pid) for i, pid in enumerate(photo_ids, start=1)]


def _body(photoshoot_id, **changes):
    return {"photoshootId": photoshoot_id, "styleText": TEXT, "songId": SONG_ID, **changes}


def _ready_draft(n=6):
    """A draft with a stored, ready plan of n shots; returns (job_id, photo_ids)."""
    photoshoot_id, photo_ids = add_ready_shoot(n)
    job_id = add_draft_job(photoshoot_id, SONG_ID, plan_status="ready")
    shots = [PlannedShot.model_validate(s) for s in _plan(photo_ids)]
    store.replace_plan(job_id, shots, None)
    return job_id, photo_ids


def _row(sql, **args):
    with session_scope() as session:
        return session.execute(text(sql), args).one()


def _shot_rows(job_id):
    with session_scope() as session:
        return session.execute(
            text("select * from job_shots where job_id = :j order by position"), {"j": job_id}
        ).all()


def test_create_job_answers_201_draft_planning(client, stub_presets, scripted_planner):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    scripted_planner.queue(_plan(photo_ids))

    response = client.post("/api/jobs", json=_body(photoshoot_id))

    job = response.json()["job"]
    assert response.status_code == 201
    assert job["status"] == "draft"
    assert job["planStatus"] == "planning"
    assert job["styleText"] == TEXT


def test_preset_sets_fps_and_song_offset(client, stub_presets, scripted_planner):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    scripted_planner.queue(_plan(photo_ids))
    client.put(f"/api/styles/{GOLDEN}", json={"songOffsetS": 12})

    response = client.post(
        "/api/jobs", json=_body(photoshoot_id, styleId=GOLDEN, styleText=GOLDEN_TEXT)
    )

    row = _row("select fps, song_offset_s from jobs where id = :j", j=response.json()["job"]["id"])
    assert response.status_code == 201
    assert (row.fps, row.song_offset_s) == (24, 12.0)


def test_photographer_edits_plan(client, stub_presets):
    job_id, photo_ids = _ready_draft()
    shots = _plan(photo_ids)[:5]
    shots[2] = planned_shot(3, photo_ids[2], movementName="crane_up")

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": shots})

    body = response.json()["job"]
    assert response.status_code == 200
    assert len(body["shots"]) == 5
    assert body["shots"][2]["movementName"] == "crane_up"
    assert body["shots"][2]["planNote"] == "Shot 3 note."
    assert len(client.get(f"/api/jobs/{job_id}").json()["job"]["shots"]) == 5


def test_bad_edit_names_the_shot(client, stub_presets):
    job_id, photo_ids = _ready_draft()
    shots = _plan(photo_ids)
    shots[1] = planned_shot(2, photo_ids[1], lengthS=12.0)

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": shots})

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_plan"
    assert "Shot 2" in response.json()["message"]
    assert len(_shot_rows(job_id)) == 6


def test_photo_from_another_shoot_is_named(client, stub_presets):
    job_id, photo_ids = _ready_draft()
    _, other_ids = add_ready_shoot(1)
    shots = _plan(photo_ids)
    shots[3] = planned_shot(4, other_ids[0])

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": shots})

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_plan"
    assert "Shot 4" in response.json()["message"]


def test_edit_while_planning_is_refused(client, stub_presets):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    job_id = add_draft_job(photoshoot_id, SONG_ID, plan_status="planning")

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": _plan(photo_ids)})

    assert response.status_code == 409
    assert response.json()["error"] == "plan_not_ready"


def test_edit_makes_a_failed_plan_ready(client, stub_presets):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    job_id = add_draft_job(photoshoot_id, SONG_ID, plan_status="planning")
    store.set_plan_failed(job_id, "The planner's plan was invalid twice.")

    response = client.put(f"/api/jobs/{job_id}/shots", json={"shots": _plan(photo_ids)})

    assert response.status_code == 200
    assert response.json()["job"]["planStatus"] == "ready"


def test_replan_from_new_text(client, stub_presets, scripted_planner):
    job_id, photo_ids = _ready_draft()
    scripted_planner.queue(_plan(photo_ids)[:4])

    response = client.post(f"/api/jobs/{job_id}/plan", json={"styleText": "Fast crane moves"})

    assert response.status_code == 202
    assert response.json()["job"]["planStatus"] == "planning"
    assert response.json()["job"]["styleText"] == "Fast crane moves"
    planning.wait_idle()
    body = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert body["styleText"] == "Fast crane moves"
    assert body["planStatus"] == "ready"
    assert len(body["shots"]) == 4
    assert scripted_planner.calls[0]["style_text"] == "Fast crane moves"


def test_replan_keeps_the_new_plan_when_an_old_one_is_in_flight(
    client, stub_presets, scripted_planner, monkeypatch
):
    """Race: the old plan finishes after the new text is stored but before the new run starts."""
    photoshoot_id, photo_ids = add_ready_shoot(6)
    old_inside, old_release = threading.Event(), threading.Event()
    old_plan = [planned_shot(i, pid, planNote="OLD") for i, pid in enumerate(photo_ids, start=1)]
    new_plan = [planned_shot(i, pid, planNote="NEW") for i, pid in enumerate(photo_ids, start=1)]
    answers = [{"shots": old_plan, "notes": "old"}, {"shots": new_plan, "notes": "new"}]

    def planner(style_text, *args):
        scripted_planner.calls.append({"style_text": style_text})
        answer = answers.pop(0)
        if answer["notes"] == "old":
            old_inside.set()
            old_release.wait(10)
        return answer

    monkeypatch.setattr(planning, "plan_shots", planner)
    job_id = client.post("/api/jobs", json=_body(photoshoot_id)).json()["job"]["id"]
    assert old_inside.wait(10)

    real_start = planning.start

    def start_after_old_finishes(job):
        old_release.set()
        planning.wait_idle()  # the old run reaches its write now
        real_start(job)

    monkeypatch.setattr(planning, "start", start_after_old_finishes)
    client.post(f"/api/jobs/{job_id}/plan", json={"styleText": "Brand new text"})
    planning.wait_idle()

    body = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert body["styleText"] == "Brand new text"
    assert body["planStatus"] == "ready"
    assert {s["planNote"] for s in body["shots"]} == {"NEW"}
    assert body["planNotes"] == "new"


def test_job_keeps_its_own_text(client, stub_presets, scripted_planner):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    scripted_planner.queue(_plan(photo_ids))
    job_id = client.post(
        "/api/jobs", json=_body(photoshoot_id, styleId=GOLDEN, styleText=GOLDEN_TEXT)
    ).json()["job"]["id"]
    planning.wait_idle()
    before = client.get(f"/api/jobs/{job_id}").json()["job"]

    changed = client.put(f"/api/styles/{GOLDEN}", json={"styleText": "Changed"})

    after = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert changed.status_code == 200
    assert after["styleText"] == GOLDEN_TEXT
    assert after["shots"] == before["shots"]


def test_shoot_still_uploading_is_refused(client, stub_presets):
    photoshoot_id, _ = add_ready_shoot(6, status="awaiting_upload")

    response = client.post("/api/jobs", json=_body(photoshoot_id))

    assert response.status_code == 409
    assert response.json()["error"] == "photoshoot_not_ready"
    assert _row("select count(*) as n from jobs where photoshoot_id = :p", p=photoshoot_id).n == 0


def test_interrupted_planning_restarts_on_app_start(monkeypatch, stub_presets, scripted_planner):
    from fastapi.testclient import TestClient

    from app.config import reset_settings
    from app.main import create_app

    photoshoot_id, photo_ids = add_ready_shoot(6)
    job_id = add_draft_job(photoshoot_id, SONG_ID, plan_status="planning")
    scripted_planner.queue(_plan(photo_ids))
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()

    with TestClient(create_app()) as app_client:
        app_client.auth = DEMO_AUTH
        planning.wait_idle()
        body = app_client.get(f"/api/jobs/{job_id}").json()["job"]

    assert body["planStatus"] == "ready"
    assert len(body["shots"]) == 6
    assert len(scripted_planner.calls) == 1
    assert scripted_planner.calls[0]["ids"]["jobId"] == job_id


def test_reproduction_is_marked(client, stub_presets, scripted_planner):
    photoshoot_id, photo_ids = add_ready_shoot(6)
    scripted_planner.queue(_plan(photo_ids))

    response = client.post(
        "/api/jobs",
        json=_body(photoshoot_id, styleId=GOLDEN, styleText=GOLDEN_TEXT, purpose="reproduction"),
    )

    job_id = response.json()["job"]["id"]
    assert response.status_code == 201
    assert response.json()["job"]["purpose"] == "reproduction"
    assert _row("select purpose from jobs where id = :j", j=job_id).purpose == "reproduction"


def test_ch1_plan_cannot_change_after_submit(client, stub_presets, scripted_planner):
    job_id, photo_ids = _ready_draft()
    with session_scope() as session:
        session.execute(text("update jobs set status = 'queued' where id = :j"), {"j": job_id})
    before = [tuple(r) for r in _shot_rows(job_id)]

    put = client.put(f"/api/jobs/{job_id}/shots", json={"shots": _plan(photo_ids)[:3]})
    post = client.post(f"/api/jobs/{job_id}/plan", json={"styleText": "Other text"})

    assert (put.status_code, put.json()["error"]) == (409, "not_draft")
    assert (post.status_code, post.json()["error"]) == (409, "not_draft")
    assert [tuple(r) for r in _shot_rows(job_id)] == before
    assert scripted_planner.calls == []


def test_whitespace_text_is_refused(client, stub_presets):
    photoshoot_id, _ = add_ready_shoot(6)

    response = client.post("/api/jobs", json=_body(photoshoot_id, styleText="   \n "))

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_style"


def test_unknown_style_is_404(client, stub_presets):
    photoshoot_id, _ = add_ready_shoot(6)

    response = client.post("/api/jobs", json=_body(photoshoot_id, styleId="nope"))

    assert response.status_code == 404
    assert response.json()["error"] == "style_not_found"


def test_unknown_song_is_404(client, stub_presets):
    photoshoot_id, _ = add_ready_shoot(6)

    response = client.post("/api/jobs", json=_body(photoshoot_id, songId="nope"))

    assert response.status_code == 404
    assert response.json()["error"] == "song_not_found"
