"""Synthetic ids and objects for tests (moved out of app/ by S27)."""

from app.shared.enums import JobStatus, ShotStatus
from app.shared.types import Job, JobListItem, JobShot, JobVideo, Photo, Song, Style

GOLDEN_HOUR_ID = "11111111-1111-4111-8111-111111111111"
CRISP_MODERN_ID = "22222222-2222-4222-8222-222222222222"
STUB_SONG_ID = "33333333-3333-4333-8333-333333333333"
STUB_DEMO_PHOTOSHOOT_ID = "44444444-4444-4444-8444-444444444444"
STUB_REFERENCE_JOB_ID = "55555555-5555-4555-8555-555555555555"

STUB_SONG = Song(
    id=STUB_SONG_ID,
    title="Sunrise Walk",
    artist="Example Artist",
    licence_code="BY-NC",
    source_url="stub://songs/sunrise-walk",
    duration_s=120.0,
    credit="Sunrise Walk, Example Artist, CC BY-NC 4.0, stub://songs/sunrise-walk",
)

STUB_STYLES = [
    Style(
        id=GOLDEN_HOUR_ID,
        name="Golden hour",
        author_name="AutoHDR",
        style_text="Slow, warm and unhurried. Open on the front of the house, "
        "move through the main rooms with gentle dolly moves, and finish on a wide exterior.",
        song=STUB_SONG,
        song_offset_s=0.0,
        fps=24,
        demo_photoshoot_id=STUB_DEMO_PHOTOSHOOT_ID,
        reference_job_id=STUB_REFERENCE_JOB_ID,
    ),
    Style(
        id=CRISP_MODERN_ID,
        name="Crisp modern",
        author_name="AutoHDR",
        style_text="Fast and clean. Short shots on the beat, slider moves and quick cuts, "
        "every room shown once.",
        song=STUB_SONG,
        song_offset_s=4.0,
        fps=30,
        demo_photoshoot_id=STUB_DEMO_PHOTOSHOOT_ID,
        reference_job_id=None,
    ),
]

STUB_PHOTOSHOOT_ID = "44444444-4444-4444-8444-444444444444"
STUB_PHOTO_IDS = [
    "66666666-6666-4666-8666-666666666601",
    "66666666-6666-4666-8666-666666666602",
]
STUB_LABEL = "12 Oak Street"


def stub_photos() -> list[Photo]:
    rooms = ["exterior_front", "living"]
    return [
        Photo(
            id=photo_id,
            position=index,
            original_name=f"photo-{index + 1}.jpg",
            content_type="image/jpeg",
            size_bytes=2_000_000,
            status="uploaded",
            room=rooms[index],
            subject=f"stub subject {index + 1}",
            thumb_url=f"/stub-media/thumb-{index + 1}.jpg",
        )
        for index, photo_id in enumerate(STUB_PHOTO_IDS)
    ]


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
