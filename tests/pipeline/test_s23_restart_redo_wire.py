"""Recovery actions across real HTTP, Jobs, Pipeline, Providers, Files and Comparison."""

# ruff: noqa: F811

from collections import Counter

import pytest

from app.files.client import get_client
from app.jobs import queue
from app.media import service as media
from app.pipeline import runner
from tests.support.fixtures import client  # noqa: F401
from tests.support.s23_world import s23_world  # noqa: F401
from tests.support.worker_rows import rows


def passed_assets(job_id, bucket):
    """Capture persisted identity and actual stored bytes, not expiring signed URLs."""
    shots = rows(
        "select s.position, s.round, s.final_attempt_id, a.clip_key from job_shots s "
        "join attempts a on a.id=s.final_attempt_id where s.job_id=:j order by s.position",
        j=job_id,
    )
    return {
        s["position"]: (
            s["round"],
            s["final_attempt_id"],
            s["clip_key"],
            get_client().get_object(Bucket=bucket, Key=s["clip_key"])["Body"].read(),
        )
        for s in shots
    }


def assert_delivery(job_id, tmp_path):
    job = queue.get_job(job_id)
    assert job.status == "ready"
    key = rows("select video_key from jobs where id=:j", j=job_id)[0]["video_key"]
    from app.files import service as files

    output = tmp_path / "delivered.mp4"
    files.get(key, str(output))
    probe = media.probe(str(output))
    assert probe["durationS"] == pytest.approx(16, abs=1 / 24)
    assert (probe["width"], probe["height"]) == (1920, 1080)
    assert rows("select * from cut_checks where job_id=:j", j=job_id)
    assert not rows(
        "select a.id from attempts a join job_shots s on s.id=a.job_shot_id "
        "where s.job_id=:j and a.attempt_no > 4",
        j=job_id,
    )
    return job


def test_restart_keeps_passed_assets_and_generates_only_unfinished(
    s23_world, client, bucket, monkeypatch, tmp_path
):
    job_id, api = s23_world
    monkeypatch.setenv("SHOTS_IN_FLIGHT", "1")
    from app.config import reset_settings

    reset_settings()
    api.errors["green"] = 402
    assert client.post(f"/api/jobs/{job_id}/submit").status_code == 202
    assert runner.run_next_job()
    before = passed_assets(job_id, bucket)
    assert set(before) == {1, 2}
    history = rows("select * from attempts order by id")
    assert queue.get_job(job_id).stop_reason == "out_of_credit"
    api.errors.clear()

    response = client.post(f"/api/jobs/{job_id}/restart")

    assert response.status_code == 202
    queued = response.json()["job"]
    assert queued["stopReason"] is None
    assert [s["clipUrl"] for s in queued["shots"][2:]] == [None, None]
    assert passed_assets(job_id, bucket) == before
    assert runner.run_next_job()
    assert api.generations == Counter(red=1, blue=1, green=2, yellow=1)
    after = passed_assets(job_id, bucket)
    assert {p: after[p] for p in before} == before
    assert [after[p][0] for p in (1, 2, 3, 4)] == [0, 0, 1, 1]
    current = {a["id"]: a for a in rows("select * from attempts")}
    assert all(current[a["id"]] == a for a in history)
    job = assert_delivery(job_id, tmp_path)
    assert job.video.version == 1
    print(
        "Restart: HTTP 202; shots 1/2 retain attempt IDs, keys and bytes; "
        "only 3/4 made; 16s video v1"
    )


def test_redo_second_shot_reuses_other_clips_and_increments_version_once(
    s23_world, client, bucket, tmp_path
):
    job_id, api = s23_world
    assert client.post(f"/api/jobs/{job_id}/submit").status_code == 202
    assert runner.run_next_job()
    before = passed_assets(job_id, bucket)
    original = assert_delivery(job_id, tmp_path)
    # A different provider output proves the selected shot really was replaced.
    api.clips["blue"] = api.clips["magenta"]

    response = client.post(f"/api/jobs/{job_id}/shots/2/redo")

    assert response.status_code == 202
    assert response.json()["job"]["shots"][1]["clipUrl"] is None
    assert runner.run_next_job()
    after = passed_assets(job_id, bucket)
    assert api.generations == Counter(red=1, blue=2, green=1, yellow=1)
    assert {p: after[p] for p in (1, 3, 4)} == {p: before[p] for p in (1, 3, 4)}
    assert after[2][0] == before[2][0] + 1
    assert all(after[2][i] != before[2][i] for i in (1, 2, 3))
    final = assert_delivery(job_id, tmp_path)
    assert final.video.version == original.video.version + 1
    assert not runner.run_next_job()
    assert queue.get_job(job_id).video.version == final.video.version
    print(
        "Redo shot 2: only blue generated twice; other clip identities/bytes unchanged; "
        "16s video v1 -> v2"
    )
