"""Real photo reads, image processing, bucket writes and persisted edit outcomes."""

from dataclasses import replace
from threading import Event

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db.base import session_scope
from app.jobs import worker_interface as jobs
from app.media import service as media
from app.photoshoots import service as photoshoots
from app.pipeline import prepare
from app.providers import fake
from tests.photoshoots.conftest import seed_shoot
from tests.pipeline.shot_world import changed_check
from tests.support.library_rows import add_song
from tests.support.worker_rows import add_job, add_shot, rows


@pytest.mark.parametrize("outcome", ["edited", "changed", "fallback", "changed_then_error"])
def test_stored_photo_is_edited_safely(bucket, tmp_path, outcome):
    fake.reset()
    shoot, (photo,) = seed_shoot(["uploaded"])
    job_id = add_job(shoot, add_song())
    shot_id = add_shot(job_id, 1, photo)
    with session_scope() as session:
        session.execute(
            text("update job_shots set photo_edit_prompts=:p where id=:s"),
            {"p": '["brighten", "straighten"]', "s": shot_id},
        )
    original = photoshoots.photo_bytes(shoot, photo)
    crop = media.crop16x9(original)
    if outcome in ("changed", "changed_then_error"):
        fake.answer_on("check_edit", 1, changed_check())
        fake.answer_on("check_edit", 2, changed_check())
    if outcome == "fallback":
        fake.fail_on("edit_photo", 2, "refused")
    if outcome == "changed_then_error":
        fake.fail_on("edit_photo", 3, "failed")
    job = jobs.claim_next_job()
    try:
        frame = prepare.first_frame(job_id, shoot, job.shots[0], 0, tmp_path)
        record = rows("select * from job_shots where id=:s", s=shot_id)[0]
        assert photoshoots.photo_bytes(shoot, photo) == original
        assert record["cropped_key"] == f"jobs/{job_id}/shots/1/r0/cropped.jpg"
        if outcome in ("changed", "changed_then_error"):
            assert frame == crop
            assert record["edit_status"] == "crop_only"
            assert record["edited_key"] is None
            assert record["edit_note"]
        else:
            assert record["edit_status"] == "edited"
            assert record["edited_key"] == f"jobs/{job_id}/shots/1/r0/edited.jpg"
        edits = rows(
            "select model from provider_calls where job_id=:j and kind='edit_photo' "
            "order by started_at",
            j=job_id,
        )
        if outcome == "fallback":
            settings = get_settings()
            assert [r["model"] for r in edits] == [settings.ENHANCE_MODEL] * 2 + [
                settings.ENHANCE_MODEL_FALLBACK
            ] * 2
        if outcome == "changed_then_error":
            assert len(edits) == 3
    finally:
        fake.reset()


@pytest.mark.parametrize("stop_during", ["edit", "check", "fallback", "retry"])
def test_concurrent_credit_stop_prevents_more_photo_calls(bucket, monkeypatch, stop_during):
    from app.pipeline import runner
    from app.providers import interface as providers
    from app.providers.errors import ProviderError
    from app.shared.enums import ProviderErrorKind

    shoot, photos = seed_shoot(["uploaded", "uploaded"])
    job_id = add_job(shoot, add_song())
    first = add_shot(job_id, 1, photos[0])
    second = add_shot(job_id, 2, photos[1])
    with session_scope() as session:
        session.execute(
            text("update job_shots set photo_edit_prompts=:p where job_id=:j"),
            {
                "p": '["brighten"]' if stop_during == "check" else '["brighten", "straighten"]',
                "j": job_id,
            },
        )
    entered = Event()
    stopped = Event()
    calls = []
    stop_job = jobs.stop_job

    def stop_and_signal(*args):
        stop_job(*args)
        stopped.set()

    def edit(jpeg, prompt, ids, model):
        if ids["jobShotId"] == second:
            assert entered.wait(5)
            raise ProviderError(ProviderErrorKind.out_of_credit, "No credit")
        calls.append(prompt)
        if stop_during != "retry":
            entered.set()
            assert stopped.wait(5)
        if stop_during == "fallback":
            raise ProviderError(ProviderErrorKind.failed, "Edit failed")
        return jpeg

    def check(*args):
        calls.append("check")
        entered.set()
        assert stopped.wait(5)
        return changed_check()

    monkeypatch.setattr(jobs, "stop_job", stop_and_signal)
    monkeypatch.setattr(providers, "edit_photo", edit)
    monkeypatch.setattr(providers, "check_edit", check)
    monkeypatch.setattr(runner, "get_settings", lambda: replace(get_settings(), SHOTS_IN_FLIGHT=2))

    assert runner.run_next_job()

    assert calls == (
        ["brighten", "straighten", "check"] if stop_during == "retry" else ["brighten"]
    )
    record = rows("select * from jobs where id=:j", j=job_id)[0]
    assert (record["status"], record["stop_reason"]) == ("stopped", "out_of_credit")
    assert (
        rows("select edit_status from job_shots where id=:s", s=first)[0]["edit_status"] != "edited"
    )
