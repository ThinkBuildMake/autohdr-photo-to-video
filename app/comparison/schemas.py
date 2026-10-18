"""Comparison request and response shapes."""

from app.shared.types import CamelModel


class ReferenceRequest(CamelModel):
    job_id: str


class VideoRef(CamelModel):
    job_id: str
    video_url: str
    photoshoot_label: str | None


class SongSame(CamelModel):
    same_song: bool
    credit: str


class VideoSummary(CamelModel):
    shot_count: int
    total_s: float
    median_shot_s: float
    movements: dict[str, int]
    transitions: dict[str, int]


class Summary(CamelModel):
    reference: VideoSummary
    reproduction: VideoSummary


class ShotTiming(CamelModel):
    length_s: float
    cut_error_s: float | None


class ShotRow(CamelModel):
    position: int
    movement_name: str
    transition: str
    reference: ShotTiming | None
    reproduction: ShotTiming | None
    flagged: bool


class Reproduction(CamelModel):
    reference: VideoRef
    reproduction: VideoRef
    song: SongSame
    same_text: bool
    summary: Summary
    shots: list[ShotRow]
    max_cut_error_s: float | None
