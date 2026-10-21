"""createStyle, setReference and getReproduction across the real Library, Jobs and Comparison."""

from sqlalchemy import text

from app.db.base import session_scope
from tests.photoshoots.conftest import object_keys
from tests.support.fixtures import client as client_fixture
from tests.support.style_flow import style_world

api_client = client_fixture

TEXT = "Slow rooms. End wide."


def make_style(client, world):
    created = client.post(
        "/api/styles",
        json={
            "name": "Flow style",
            "authorName": "Sam",
            "styleText": TEXT,
            "songId": world.song_id,
            "demoPhotoshootId": world.shoots[0],
            "fps": 30,
            "videoUrl": "https://outside.invalid/video.mp4",
        },
    )
    assert created.status_code == 201
    return created.json()["style"]["id"]


def make_job(client, world, style_id, shoot, purpose):
    created = client.post(
        "/api/jobs",
        json={
            "photoshootId": shoot,
            "styleId": style_id,
            "styleText": TEXT,
            "songId": world.song_id,
            "purpose": purpose,
        },
    )
    assert created.status_code == 201
    return created.json()["job"]["id"]


def test_style_reference_and_reproduction_use_only_internal_objects(
    api_client, bucket, tmp_path, monkeypatch
):
    with style_world(tmp_path, monkeypatch) as world:
        style_id = make_style(api_client, world)
        tries = [
            world.finish(make_job(api_client, world, style_id, world.shoots[0], "video")).id
            for _ in range(2)
        ]
        assert (
            api_client.post(
                f"/api/styles/{style_id}/reference", json={"jobId": tries[1]}
            ).status_code
            == 200
        )
        reproduction = world.finish(
            make_job(api_client, world, style_id, world.shoots[1], "reproduction")
        ).id

        body = api_client.get(f"/api/styles/{style_id}/reproductions/{reproduction}").json()

        assert body["reference"]["jobId"] == tries[1]
        assert body["reproduction"]["jobId"] == reproduction
        assert body["sameText"] is True and body["song"]["sameSong"] is True
        assert (
            body["summary"]["reference"]["shotCount"]
            == body["summary"]["reproduction"]["shotCount"]
            == 1
        )
        assert (
            api_client.get(f"/api/styles/{style_id}").json()["style"]["referenceJobId"] == tries[1]
        )
        # Every stored object and every key a job points at is under an allowed prefix.
        with session_scope() as session:
            pointed = (
                session.execute(text("select video_key from jobs where video_key is not null"))
                .scalars()
                .all()
            )
        keys = [*object_keys(), *pointed]
        assert len(pointed) == 3
        assert any(k.startswith("jobs/") for k in keys)
        assert all(k.startswith(("photoshoots/", "jobs/", "songs/")) for k in keys), keys
        assert not any("outside.invalid" in k for k in keys)


def test_a_style_with_no_reference_cannot_be_compared(api_client, bucket, tmp_path, monkeypatch):
    with style_world(tmp_path, monkeypatch) as world:
        style_id = make_style(api_client, world)
        job = world.finish(
            make_job(api_client, world, style_id, world.shoots[1], "reproduction")
        ).id

        response = api_client.get(f"/api/styles/{style_id}/reproductions/{job}")

        assert response.status_code == 409
        assert response.json()["error"] == "no_reference"


def test_a_job_that_is_not_ready_cannot_be_the_reference(api_client, bucket, tmp_path, monkeypatch):
    with style_world(tmp_path, monkeypatch) as world:
        style_id = make_style(api_client, world)
        waiting = make_job(api_client, world, style_id, world.shoots[0], "video")

        response = api_client.post(f"/api/styles/{style_id}/reference", json={"jobId": waiting})

        assert response.status_code == 409
        assert response.json()["error"] == "not_eligible"
        assert api_client.get(f"/api/styles/{style_id}").json()["style"]["referenceJobId"] is None
