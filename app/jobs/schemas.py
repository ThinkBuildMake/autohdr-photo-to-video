"""Jobs request and response shapes."""

from typing import Literal

from app.shared.types import CamelModel, Job, JobListItem, JobShot, PlannedShot


class JobCreate(CamelModel):
    photoshoot_id: str
    style_text: str
    song_id: str
    style_id: str | None = None
    purpose: Literal["video", "reproduction"] = "video"


class JobReplan(CamelModel):
    style_text: str | None = None
    song_id: str | None = None


class JobShotsUpdate(CamelModel):
    shots: list[PlannedShot]


class ShotEdit(CamelModel):
    photo_id: str | None = None
    movement_name: str | None = None
    movement_prompt: str | None = None
    speed: str | None = None
    photo_edit_prompts: list[str] | None = None
    length_s: float | None = None
    transition: str | None = None
    transition_s: float | None = None
    removed: bool | None = None


class JobOne(CamelModel):
    job: Job


class JobList(CamelModel):
    jobs: list[JobListItem]


class ExportPlan(CamelModel):
    new_clips: int
    recut_only: int
    removed: int


class ShotEditResult(CamelModel):
    shot: JobShot
    export_plan: ExportPlan


class VideoLinks(CamelModel):
    url: str
    download_url: str
    duration_s: float
