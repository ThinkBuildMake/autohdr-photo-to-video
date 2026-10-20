"""Stub data for the Jobs contract. S09-S11 replace it with the database.

photoshoot_status, list_photos, allowed_lengths and plan_shots stand in for
Photoshoots.listPhotos, Providers.planShots and Providers.allowedLengths; S21 removes them.
"""

from sqlalchemy import select

from app.config import get_settings
from app.db.base import session_scope
from app.jobs.plan_rules import MOVEMENTS
from app.library.stubs import GOLDEN_HOUR_ID, STUB_REFERENCE_JOB_ID, STUB_SONG
from app.photoshoots.models import Photo, Photoshoot
from app.photoshoots.stubs import STUB_PHOTO_IDS, STUB_PHOTOSHOOT_ID
from app.shared.enums import JobStatus, ShotStatus
from app.shared.types import Job, JobListItem, JobShot, JobVideo, PlannedShot

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
        video=JobVideo(
            url="/stub-media/video.mp4", duration_s=6.0, width=1920, height=1080, version=1
        ),
        song_credit=STUB_SONG.credit,
    )


def stub_video_links() -> dict:
    return {
        "url": "/stub-media/video.mp4",
        "download_url": "/stub-media/video.mp4",
        "duration_s": 6.0,
    }


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


def photoshoot_status(photoshoot_id: str) -> str | None:
    with session_scope() as session:
        return session.scalar(select(Photoshoot.status).where(Photoshoot.id == photoshoot_id))


def list_photos(photoshoot_id: str) -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Photo.id, Photo.room, Photo.subject)
            .where(Photo.photoshoot_id == photoshoot_id, Photo.status == "uploaded")
            .order_by(Photo.position)
        ).all()
    return [{"photoId": r.id, "room": r.room, "subject": r.subject, "jpegBytes": b""} for r in rows]


def allowed_lengths(model: str) -> list[float]:
    if model == "google/veo-3.1":
        return [4.0, 6.0, 8.0]
    if model == "bytedance/seedance-2.0":
        return [float(n) for n in range(4, 16)]
    return []


def plan_shots(
    style_text: str,
    song_duration_s: float,
    photos: list[dict],
    movements: dict[str, str],
    allowed_lengths: list[float],
    ids: dict,
) -> dict:
    length = 4.0
    count = min(len(photos), max(1, int(song_duration_s // length)))
    model = get_settings().VIDEO_MODEL
    shots = [
        PlannedShot(
            position=i,
            room=photo.get("room") or "other",
            photo_id=photo["photoId"],
            photo_edit_prompts=[],
            movement_name="dolly_in",
            movement_prompt=MOVEMENTS["dolly_in"],
            speed="slow",
            model=model,
            length_s=length,
            transition="cut",
            transition_s=0.0,
            plan_note="One shot per photo, in upload order.",
        )
        for i, photo in enumerate(photos[:count], start=1)
    ]
    return {"shots": shots, "notes": ""}
