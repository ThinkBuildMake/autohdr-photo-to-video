"""Worker lifecycle with real Jobs, Media, moto Files and audited fake providers."""

import wave

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db.base import session_scope
from app.files import service as files
from app.media import service as media
from app.pipeline import runner
from app.providers import calls as clip_calls
from app.providers import fake, fake_video
from tests.photoshoots.conftest import seed_shoot
from tests.pipeline.clip_world import flagged_check
from tests.support.library_rows import add_song
from tests.support.worker_rows import add_job, add_shot, rows


@pytest.mark.parametrize("fps", [24, 30])
def test_worker_delivers_probed_video_and_complete_audit(bucket, tmp_path, monkeypatch, fps):
    finish_ok = clip_calls.finish_ok
    monkeypatch.setattr(
        clip_calls,
        "finish_ok",
        lambda call_id, cost, source, *rest: finish_ok(call_id, 0.25, source, *rest),
    )
    fake.reset()
    fake_video.reset()
    shoot, (photo,) = seed_shoot(["uploaded"])
    song = add_song()
    song_path = tmp_path / "song.wav"
    with wave.open(str(song_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 5)
    files.put(f"songs/{song}.wav", str(song_path))
    job_id = add_job(shoot, song, submitted_at="2026-10-20T10:00:00Z")
    shot_id = add_shot(job_id, 1, photo)
    with session_scope() as session:
        session.execute(
            text("update songs set file_key=:k where id=:s"), {"k": f"songs/{song}.wav", "s": song}
        )
        session.execute(text("update jobs set fps=:f where id=:j"), {"f": fps, "j": job_id})
        session.execute(
            text("update job_shots set photo_edit_prompts=:p where id=:s"),
            {"p": '["brighten"]', "s": shot_id},
        )
    fake_video.fail_on(1, "refused")
    fake.answer_on("check_clip", 1, flagged_check())
    try:
        assert runner.run_next_job() is True
        job = rows("select * from jobs where id=:j", j=job_id)[0]
        assert job["status"] == "ready"
        downloaded = str(tmp_path / "delivered.mp4")
        files.get(job["video_key"], downloaded)
        probe = media.probe(downloaded)
        assert (probe["width"], probe["height"], probe["fps"]) == (1920, 1080, fps)
        assert probe["durationS"] == pytest.approx(3, abs=1 / fps)
        shot = rows("select * from job_shots where id=:s", s=shot_id)[0]
        attempts = rows(
            "select * from attempts where job_shot_id=:s order by attempt_no", s=shot_id
        )
        assert [a["status"] for a in attempts] == ["error", "flagged", "passed"]
        assert shot["final_attempt_id"] == attempts[2]["id"]
        assert (shot["photo_id"], shot["edit_status"], shot["photo_edit_prompts"]) == (
            photo,
            "edited",
            '["brighten"]',
        )
        assert attempts[1]["check_ai_score"] == 0.8
        assert attempts[1]["check_match_score"] == 0.4
        assert all(a["started_at"] and a["finished_at"] and a["round"] == 0 for a in attempts)
        assert all("Camera speed:" in a["prompt"] for a in attempts)
        assert attempts[2]["model"] == get_settings().VIDEO_MODEL_FALLBACK
        calls = rows("select * from provider_calls where job_id=:j", j=job_id)
        assert job["total_cost_usd"] == sum(c["cost_usd"] or 0 for c in calls)
        assert job["total_cost_usd"] > 0
        assert job["started_at"] and job["finished_at"] and job["first_finished_at"]
        assert len(attempts) <= 4
        print(
            f"delivered {probe}; attempts=error,flagged,passed; "
            f"final=passed; cost={job['total_cost_usd']}"
        )
    finally:
        fake.reset()
        fake_video.reset()


@pytest.mark.parametrize("guard", ["cap", "deadline"])
def test_persisted_retries_obey_cap_and_shared_deadline(bucket, tmp_path, monkeypatch, guard):
    from datetime import UTC, datetime, timedelta

    from app.pipeline import run

    fake.reset()
    fake_video.reset()
    shoot, (photo,) = seed_shoot(["uploaded"])
    job_id = add_job(shoot, add_song())
    shot_id = add_shot(job_id, 1, photo)
    for number in range(1, 5):
        fake.answer_on("check_clip", number, flagged_check())
    if guard == "deadline":
        ticks = iter([0, 0, 29])
        start = datetime.now(UTC)
        monkeypatch.setattr(run, "now_utc", lambda: start + timedelta(minutes=next(ticks, 29)))
    try:
        runner.run_next_job()
        job = rows("select * from jobs where id=:j", j=job_id)[0]
        shot = rows("select * from job_shots where id=:s", s=shot_id)[0]
        attempts = rows("select * from attempts where job_shot_id=:s", s=shot_id)
        assert job["stop_reason"] == "no_shot_passed"
        assert job["video_key"] is None
        assert shot["final_attempt_id"] is None
        assert len(attempts) == (4 if guard == "cap" else 1)
        assert all(a["status"] == "flagged" and a["check_ai_score"] == 0.8 for a in attempts)
        assert shot["failure_reason"] == (
            "flagged_every_attempt" if guard == "cap" else "out_of_time"
        )
    finally:
        fake.reset()
        fake_video.reset()
