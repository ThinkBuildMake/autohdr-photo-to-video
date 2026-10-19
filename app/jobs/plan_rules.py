"""Shot-plan rules: the starter-kit movements and the checks a plan must pass."""

import math
from collections.abc import Callable

from app.shared.types import PlannedShot

# PRD pp.8-9 starter kit, keyed by MovementName value.
MOVEMENTS: dict[str, str] = {
    "dolly_in": "Super smooth camera moves forward in straight line through space, cinematic",
    "dolly_in_timelapse": (
        "Super smooth camera moves forward in straight line through space,"
        "time-lapse light progression, shadows gradually move and lengthen, parallax effect, "
        "consistent exposure, stable motion, cinematic, photorealistic"
    ),
    "drone_top_down_descend": (
        "Super smooth camera descends in a straight line through space, cinematic"
    ),
    "timelapse_variant": (
        "Super smooth camera moves forward in straight line through space, cinematic. "
        "As time progresses, the sun lowers as the day progresses as a timelapse."
    ),
    "dolly_out": "Super smooth camera moves backward in straight line revealing space, cinematic",
    "slider_truck_left_to_right": (
        "Super smooth camera glides horizontally from left to right, parallel path, cinematic"
    ),
    "slider_truck_right_to_left": (
        "Super smooth camera glides horizontally from right to left, parallel path, cinematic"
    ),
    "parallax_orbit": (
        "Super smooth camera travels in arc around subject, subject stays centered, cinematic"
    ),
    "dolly_in_pan_right": (
        "Super smooth camera moves forward while rotating gradually right, curved path, cinematic"
    ),
    "crane_up": "Super smooth camera rises vertically upward, straight vertical path, cinematic",
    "crane_down": (
        "Super smooth camera descends vertically downward, straight vertical path, cinematic"
    ),
    "orbit_hyperlapse": (
        "Super smooth camera travels in arc around subject, subject stays centered, "
        "sky hyperlapses naturally in the background, cinematic"
    ),
}
SPEEDS = ("slow", "medium", "fast")
TRANSITIONS = ("cut", "crossfade")


def _num(value: float) -> str:
    return f"{value:g}"


def validate_plan(
    shots: list[PlannedShot],
    photo_ids: set[str],
    song_budget_s: float,
    lengths_for: Callable[[str], list[float]],
) -> list[str]:
    """One message per problem; shot messages start 'Shot {n}:' (1-based place in the list)."""
    problems: list[str] = []
    if not shots:
        return ["The plan has no shots."]
    total = 0.0
    for n, shot in enumerate(shots, start=1):
        prefix = f"Shot {n}:"
        if not (math.isfinite(shot.length_s) and math.isfinite(shot.transition_s)):
            problems.append(f"{prefix} the length and transition length must be finite numbers.")
            continue
        if shot.movement_name not in MOVEMENTS:
            problems.append(f"{prefix} unknown movement '{shot.movement_name}'.")
        if shot.speed not in SPEEDS:
            problems.append(f"{prefix} unknown speed '{shot.speed}'.")
        if shot.transition not in TRANSITIONS:
            problems.append(f"{prefix} unknown transition '{shot.transition}'.")
        elif shot.transition == "cut" and shot.transition_s != 0:
            problems.append(f"{prefix} a cut must have a transition length of 0.")
        elif shot.transition == "crossfade" and shot.transition_s <= 0:
            problems.append(f"{prefix} a crossfade must have a transition length above 0.")
        if shot.length_s <= 0:
            problems.append(f"{prefix} the length must be above 0.")
        lengths = lengths_for(shot.model)
        if not lengths:
            problems.append(f"{prefix} unknown model '{shot.model}'.")
        else:
            longest = max(lengths)
            needed = shot.length_s + shot.transition_s
            if needed > longest:
                problems.append(
                    f"{prefix} {_num(needed)} s is longer than {shot.model}'s "
                    f"longest clip, {_num(longest)} s."
                )
        if shot.photo_id is not None:
            if shot.photo_id not in photo_ids:
                problems.append(f"{prefix} photo {shot.photo_id} is not in this photoshoot.")
            total += shot.length_s
    if total > song_budget_s:
        problems.append(
            f"The shots total {_num(total)} s, longer than the song's {_num(song_budget_s)} s."
        )
    return problems


def renumber(shots: list[PlannedShot]) -> list[PlannedShot]:
    """Sort by position and set positions 1..n."""
    ordered = sorted(shots, key=lambda s: s.position)
    return [s.model_copy(update={"position": i}) for i, s in enumerate(ordered, start=1)]
