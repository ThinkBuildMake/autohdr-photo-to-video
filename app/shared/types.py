"""Contract types shared across modules (ARCHITECTURE: Shared types).

JSON keys are camelCase; Python attributes are snake_case.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.shared.enums import FailureReason, JobStatus, Room, ShotStatus, StopReason


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Song(CamelModel):
    id: str
    title: str
    artist: str
    licence_code: str
    source_url: str
    duration_s: float
    credit: str


class Style(CamelModel):
    id: str
    name: str
    author_name: str
    style_text: str
    song: Song
    song_offset_s: float
    fps: int
    demo_photoshoot_id: str | None
    reference_job_id: str | None


class StyleSummary(CamelModel):
    id: str
    name: str
    author_name: str
    style_text: str
    song: Song
    has_reference: bool


class Photo(CamelModel):
    id: str
    position: int
    original_name: str
    content_type: str
    size_bytes: int
    status: Literal["awaiting_upload", "uploaded", "missing", "too_large"]
    room: Room | None
    subject: str | None
    thumb_url: str


class PlannedShot(CamelModel):
    position: int
    room: Room
    photo_id: str | None
    photo_edit_prompts: list[str]
    movement_name: str
    movement_prompt: str
    speed: str
    model: str
    length_s: float
    transition: str
    transition_s: float
    plan_note: str


class JobShot(CamelModel):
    id: str
    position: int
    room: Room
    movement_name: str
    movement_prompt: str
    speed: str
    photo_edit_prompts: list[str]
    length_s: float
    transition: str
    transition_s: float
    photo_id: str | None
    removed: bool
    pending_change: Literal["none", "new_clip", "recut_only"]
    plan_note: str
    edit_status: Literal["edited", "crop_only"] | None
    edit_note: str | None
    model: str
    used_fallback: bool
    status: ShotStatus
    status_detail: str
    failure_reason: FailureReason | None
    attempts: int
    clip_url: str | None


class JobVideo(CamelModel):
    url: str
    duration_s: float
    width: int
    height: int


class Job(CamelModel):
    id: str
    style_id: str | None
    style_name: str
    photoshoot_id: str
    purpose: Literal["video", "reproduction"]
    style_text: str
    plan_status: Literal["planning", "ready", "failed"]
    plan_notes: str | None
    status: JobStatus
    stop_reason: StopReason | None
    submitted_at: str | None
    started_at: str | None
    finished_at: str | None
    elapsed_s: float
    total_cost_usd: float
    waiting_behind: str | None
    shots: list[JobShot]
    video: JobVideo | None
    song_credit: str


class JobListItem(CamelModel):
    id: str
    style_name: str
    photoshoot_label: str | None
    purpose: Literal["video", "reproduction"]
    status: JobStatus
    submitted_at: str | None
    elapsed_s: float


class ClipResult(CamelModel):
    path: str
    seconds: float
    model: str
    cost_usd: float
    cost_source: Literal["reported", "list_price"]
    provider_request_id: str | None


class ClipCheck(CamelModel):
    ai_score: float
    match_score: float
    people_count: int
    added_objects: list[str]
    removed_objects: list[str]
    changed_objects: list[str]
    passed: bool
    notes: str


class EditCheck(CamelModel):
    added_objects: list[str]
    removed_objects: list[str]
    changed_objects: list[str]
    architecture_changed: bool
    notes: str
