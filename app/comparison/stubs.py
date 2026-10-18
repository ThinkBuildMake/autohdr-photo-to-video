"""Stub data for the Comparison contract. S13 replaces it with measured cut times."""

from app.comparison.schemas import (
    Reproduction,
    ShotRow,
    ShotTiming,
    SongSame,
    Summary,
    VideoRef,
    VideoSummary,
)
from app.library.stubs import STUB_SONG


def stub_reproduction(reference_job_id: str, job_id: str) -> Reproduction:
    summary = VideoSummary(
        shot_count=2,
        total_s=6.0,
        median_shot_s=3.0,
        movements={"dolly_in": 2},
        transitions={"cut": 2},
    )
    return Reproduction(
        reference=VideoRef(
            job_id=reference_job_id,
            video_url="/stub-media/reference.mp4",
            photoshoot_label="12 Oak Street",
        ),
        reproduction=VideoRef(
            job_id=job_id, video_url="/stub-media/video.mp4", photoshoot_label="12 Oak Street"
        ),
        song=SongSame(same_song=True, credit=STUB_SONG.credit),
        same_text=True,
        summary=Summary(reference=summary, reproduction=summary),
        shots=[
            ShotRow(
                position=position,
                movement_name="dolly_in",
                transition="cut",
                reference=ShotTiming(length_s=3.0, cut_error_s=0.0),
                reproduction=ShotTiming(length_s=3.0, cut_error_s=0.0),
                flagged=False,
            )
            for position in range(2)
        ],
        max_cut_error_s=0.0,
    )
