"""Providers interface for other modules (ARCHITECTURE: Module: Providers).

Each function dispatches to FakeProviders when FAKE_PROVIDERS is set, else to OpenRouterProviders.
ids = {"jobId", "jobShotId", "attemptId", "photoshootId"}, copied into provider_calls.
All raise ProviderError.
"""

from typing import Any

from app.config import get_settings
from app.providers.fake import FakeProviders
from app.providers.openrouter import OpenRouterProviders
from app.shared.types import ClipCheck, ClipResult, EditCheck


def _impl() -> FakeProviders | OpenRouterProviders:
    return FakeProviders() if get_settings().FAKE_PROVIDERS else OpenRouterProviders()


def label_photos(photos: list[dict], photoshoot_id: str) -> list[dict]:
    """photos: [{photoId, jpegBytes}] -> [{photoId, room, subject}]."""
    return _impl().label_photos(photos, photoshoot_id)


def plan_shots(
    style_text: str,
    song_duration_s: float,
    photos: list[dict],
    movements: dict[str, str],
    allowed_lengths: list[float],
    ids: dict[str, Any],
) -> dict:
    """Returns {shots: PlannedShot[], notes}."""
    return _impl().plan_shots(style_text, song_duration_s, photos, movements, allowed_lengths, ids)


def edit_photo(
    jpeg_bytes: bytes, prompt: str, ids: dict[str, Any], model: str | None = None
) -> bytes:
    return _impl().edit_photo(jpeg_bytes, prompt, ids, model)


def check_edit(original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, Any]) -> EditCheck:
    return _impl().check_edit(original_jpeg, edited_jpeg, ids)


def generate_clip(
    first_frame_jpeg: bytes,
    prompt: str,
    model: str,
    length_s: float,
    ids: dict[str, Any],
) -> ClipResult:
    return _impl().generate_clip(first_frame_jpeg, prompt, model, length_s, ids)


def check_clip(
    clip_path: str,
    frames: list[bytes],
    source_jpeg: bytes,
    ids: dict[str, Any],
) -> ClipCheck:
    return _impl().check_clip(clip_path, frames, source_jpeg, ids)


def allowed_lengths(model: str) -> list[float]:
    return _impl().allowed_lengths(model)


def recover_calls() -> None:
    """Called once when the worker starts."""
    _impl().recover_calls()
