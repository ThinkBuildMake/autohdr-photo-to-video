"""planShots: one chat request turns a style text and labelled photos into a shot plan."""

from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.providers import chat as chat_client
from app.shared.enums import Room
from app.shared.types import PlannedShot

SHOT_SHAPE = (
    '{"shots": [{"position": 1, "room": "kitchen", "photoId": "<photoId or null>", '
    '"photoEditPrompts": ["..."], "movementName": "<movement name>", "movementPrompt": "...", '
    '"speed": "slow", "model": "<video model>", "lengthS": 6, "transition": "cut", '
    '"transitionS": 0, "planNote": "why this shot"}], "notes": "anything the user should know"}'
)

PROMPT = (
    "You plan a real-estate video as a list of shots, in playing order. The video will run "
    "{song_duration_s:g} seconds, the length of its song, so the shot lengths (minus overlaps "
    "for transitions) should add up to about that. Each shot's lengthS must be one of: "
    "{lengths}.\n\nStyle text from the user:\n{style_text}\n\n"
    "Movements you can use (movementName: starter prompt):\n{movements}\n\n"
    "room must be one of: {rooms}. Use each photo's photoId in photoId, or null for a shot "
    "that needs no photo. photoEditPrompts lists the edits to make to that photo first (may be "
    "empty). If the style text asks for something the photos do not show, say so in notes.\n"
    "Answer with JSON only, in exactly this shape: {shape}\n\n"
    "Photos follow; each is introduced by a line with its photoId, room and subject."
)


def plan_shots(
    style_text: str,
    song_duration_s: float,
    photos: list[dict],
    movements: dict[str, str],
    allowed_lengths: list[float],
    ids: dict[str, Any],
) -> dict:
    settings = get_settings()
    prompt = PROMPT.format(
        song_duration_s=song_duration_s,
        lengths=", ".join(f"{length:g}" for length in allowed_lengths),
        style_text=style_text,
        movements="\n".join(f"- {name}: {text}" for name, text in movements.items()) or "- (any)",
        rooms=", ".join(room.value for room in Room),
        shape=SHOT_SHAPE,
    )
    content: list[dict[str, Any]] = [chat_client.text_part(prompt)]
    for photo in photos:
        content.append(
            chat_client.text_part(
                f"photoId: {photo['photoId']}; room: {photo.get('room', '')}; "
                f"subject: {photo.get('subject', '')}"
            )
        )
        content.append(chat_client.image_part(photo["jpegBytes"]))
    answer = chat_client.chat(
        "plan_shots",
        settings.PLANNER_MODEL,
        [{"role": "user", "content": content}],
        ids,
        timeout_s=120,
        json_mode=True,
    )

    def bad(message: str):
        return chat_client.bad_response(answer.call_id, message)

    parsed = chat_client.parse_json(answer.content, answer.call_id)
    raw_shots = parsed.get("shots") if isinstance(parsed, dict) else None
    if not isinstance(raw_shots, list) or not raw_shots:
        raise bad("The answer had no shots.")
    photo_ids = {photo["photoId"] for photo in photos}
    shots = []
    for index, raw in enumerate(raw_shots):
        if not isinstance(raw, dict):
            raise bad("A shot was not an object.")
        data = {
            "position": index + 1,
            "model": settings.VIDEO_MODEL,
            "transitionS": 0,
            "planNote": "",
            "photoId": None,
            "photoEditPrompts": [],
            **{key: value for key, value in raw.items() if value is not None or key == "photoId"},
        }
        try:
            shot = PlannedShot.model_validate(data)
        except ValidationError:
            raise bad("A shot was missing a field or had a wrong value.") from None
        if shot.photo_id is not None and shot.photo_id not in photo_ids:
            raise bad("A shot named a photo that was not given.")
        if movements and shot.movement_name not in movements:
            raise bad("A shot named a movement that was not offered.")
        if shot.length_s <= 0:
            raise bad("A shot had no length.")
        shots.append(shot)
    notes = parsed.get("notes")
    return {"shots": shots, "notes": notes if isinstance(notes, str) else ""}
