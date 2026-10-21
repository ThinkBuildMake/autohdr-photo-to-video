"""Library resolves internal reference jobs through real Jobs and Files reads."""

import json
import subprocess
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.library import service
from app.library.schemas import StyleCreate
from tests.photoshoots.conftest import seed_shoot
from tests.support.library_rows import add_job_row, add_song


@pytest.mark.parametrize(
    "status,key,playable",
    [
        ("ready", "jobs/reference/video.mp4", True),
        ("draft", None, False),
        ("running", "jobs/reference/video.mp4", False),
    ],
)
def test_reference_playback_is_internal_signed_media(client, bucket, status, key, playable):
    song = add_song()
    shoot, _ = seed_shoot(["uploaded"], "ready", label="Demo")
    style = service.create_style(
        StyleCreate(
            name="Style",
            author_name="Sam",
            style_text="Slow rooms",
            song_id=song,
            demo_photoshoot_id=shoot,
        )
    )
    job = add_job_row(song, style_id=style.id)
    with session_scope() as session:
        session.execute(
            text("update jobs set status=:s, video_key=:k where id=:id"),
            {"s": status, "k": key, "id": job},
        )
    service.set_reference_job(style.id, job)

    url = service.reference_video_url(style.id)

    if playable:
        assert urlparse(url).path.endswith("/jobs/reference/video.mp4")
        assert "Signature=" in url or "X-Amz-Signature=" in url
    else:
        assert url is None


def test_two_tries_keep_snapshots_and_only_internal_objects(client, bucket, tmp_path, monkeypatch):
    from app.files import service as files
    from app.media import service as media
    from tests.photoshoots.conftest import object_keys
    from tests.support.style_flow import style_world

    with style_world(tmp_path, monkeypatch) as world:
        response = client.post(
            "/api/styles",
            json={
                "name": "Demo style",
                "authorName": "Sam",
                "styleText": "Slow rooms.",
                "songId": world.song_id,
                "demoPhotoshootId": world.shoots[0],
                "fps": 30,
                "videoUrl": "https://outside.invalid/video.mp4",
            },
        )
        assert response.status_code == 201
        style_id = response.json()["style"]["id"]
        jobs = []
        for sentence in ("Slow rooms.", "Slow rooms. End wide."):
            assert (
                client.put(f"/api/styles/{style_id}", json={"styleText": sentence}).status_code
                == 200
            )
            created = client.post(
                "/api/jobs",
                json={
                    "photoshootId": world.shoots[0],
                    "styleId": style_id,
                    "styleText": sentence,
                    "songId": world.song_id,
                    "purpose": "video",
                },
            )
            assert created.status_code == 201
            jobs.append(world.finish(created.json()["job"]["id"]))
        assert jobs[0].id != jobs[1].id
        assert [job.style_text for job in jobs] == ["Slow rooms.", "Slow rooms. End wide."]
        assert (
            client.post(f"/api/styles/{style_id}/reference", json={"jobId": jobs[1].id}).status_code
            == 200
        )
        detail = client.get(f"/api/styles/{style_id}").json()
        assert detail["style"]["referenceJobId"] == jobs[1].id
        assert "/jobs/" in detail["referenceVideoUrl"]
        assert client.get("/api/styles").json()["styles"][0]["hasReference"] is True
        with session_scope() as session:
            keys = (
                session.execute(text("select video_key from jobs order by created_at"))
                .scalars()
                .all()
            )
        assert len(set(keys)) == 2
        for index, key in enumerate(keys):
            output = str(tmp_path / f"try-{index}.mp4")
            files.get(key, output)
            assert media.probe(output)["durationS"] == pytest.approx(4, abs=0.1)
            served = {}
            world.serve_media(
                SimpleNamespace(
                    request=SimpleNamespace(url=files.presign_download(key)),
                    fulfill=lambda served=served, **response: served.update(response),
                )
            )
            assert served["content_type"] == "video/webm"
            browser_video = tmp_path / f"try-{index}.webm"
            browser_video.write_bytes(served["body"])
            streams = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_streams",
                        "-of",
                        "json",
                        str(browser_video),
                    ]
                )
            )["streams"]
            assert next(s for s in streams if s["codec_type"] == "video")["codec_name"] == "vp8"
            assert media.probe(str(browser_video))["durationS"] == pytest.approx(4, abs=0.1)
        stored = object_keys()
        assert set(keys).issubset(stored)
        assert all(key.startswith(("photoshoots/", "jobs/", "songs/")) for key in stored)
        assert "CC BY-NC" in jobs[1].song_credit
        print(
            f"tries={[job.id for job in jobs]}; reference={jobs[1].id}; "
            f"snapshots={[job.style_text for job in jobs]}; keys={stored}"
        )
