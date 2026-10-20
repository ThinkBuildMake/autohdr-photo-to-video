"""A shot's clip prompt and clip length (steps 2 and 3)."""

from app.providers import interface as providers
from app.shared.types import JobShot

# VIDEO_RESEARCH.md §7.3's extra-lock sentence. The clip check, not this text, enforces VR-5.
LOCK_TEXT = (
    "There are no people anywhere in the frame, and no reflections of people, cameras or "
    "photographers in any mirror or glass. Reflections in mirrors and glass must show only the "
    "same room contents as the photo. Keep exactly the same number of ceiling vents, lights and "
    "fixtures as the photo; do not add any."
)


def build_prompt(shot: JobShot) -> str:
    return f"{shot.movement_prompt.rstrip('. ')}. Camera speed: {shot.speed}. {LOCK_TEXT}"


def clip_length(shot: JobShot) -> float:
    """The shortest allowed length covering the shot and its incoming crossfade. Plan position 1
    has no incoming transition, even when it is not the first shot being made."""
    need = round(shot.length_s + (shot.transition_s if shot.position > 1 else 0.0), 3)
    allowed = sorted(providers.allowed_lengths(shot.model))
    return next((s for s in allowed if s >= need), allowed[-1])
