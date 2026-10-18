"""Stub data for the Jobs contract. S09-S11 replace it with the database."""

from app.library.stubs import GOLDEN_HOUR_ID, STUB_REFERENCE_JOB_ID, STUB_SONG
from app.photoshoots.stubs import STUB_PHOTO_IDS, STUB_PHOTOSHOOT_ID
from app.shared.enums import JobStatus, ShotStatus
from app.shared.types import Job, JobListItem, JobShot, JobVideo

STUB_JOB_ID = STUB_REFERENCE_JOB_ID
STUB_TIME = "2026-01-01T00:00:00Z"
STUB_STYLE_TEXT = "Slow, warm and unhurried."


def stub_shot(position: int) -> JobShot:
    return JobShot(
        id=f"77777777-7777-4777-8777-77777777770{position}",
        position=position,
        room="exterior_front" if position == 0 else "living",
        movement_name="dolly_in",
        movement_prompt="Slow dolly in.",
        speed="slow",
        photo_edit_prompts=[],
        length_s=3.0,
        transition="cut",
        transition_s=0.0,
        photo_id=STUB_PHOTO_IDS[position],
        removed=False,
        pending_change="none",
        plan_note="Opens on the front of the house.",
        edit_status="crop_only",
        edit_note=None,
        model="google/veo-3.1",
        used_fallback=False,
        status=ShotStatus.passed,
        status_detail="Passed the check.",
        failure_reason=None,
        attempts=1,
        clip_url=f"/stub-media/clip-{position}.mp4",
    )


def stub_job() -> Job:
    return Job(
        id=STUB_JOB_ID,
        style_id=GOLDEN_HOUR_ID,
        style_name="Golden hour",
        photoshoot_id=STUB_PHOTOSHOOT_ID,
        purpose="video",
        style_text=STUB_STYLE_TEXT,
        plan_status="ready",
        plan_notes=None,
        status=JobStatus.ready,
        stop_reason=None,
        submitted_at=STUB_TIME,
        started_at=STUB_TIME,
        finished_at=STUB_TIME,
        elapsed_s=300.0,
        total_cost_usd=0.0,
        waiting_behind=None,
        shots=[stub_shot(0), stub_shot(1)],
        video=JobVideo(url="/stub-media/video.mp4", duration_s=6.0, width=1920, height=1080),
        song_credit=STUB_SONG.credit,
    )


def stub_list_item() -> JobListItem:
    job = stub_job()
    return JobListItem(
        id=job.id,
        style_name=job.style_name,
        photoshoot_label="12 Oak Street",
        purpose=job.purpose,
        status=job.status,
        submitted_at=job.submitted_at,
        elapsed_s=job.elapsed_s,
    )
