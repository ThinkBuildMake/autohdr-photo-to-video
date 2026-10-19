"""labelPhotos: one chat request labels every photo of a photoshoot."""

from typing import Any

from app.config import get_settings
from app.providers import chat as chat_client
from app.shared.enums import Room

PROMPT = (
    "You label real-estate photos. For each photo below give its room and a short subject "
    "(what the photo shows, e.g. 'white island with stools'). room must be one of: {rooms}. "
    'Answer with JSON only: {{"labels": [{{"photoId": "...", "room": "...", "subject": "..."}}]}}. '
    "Each photo is introduced by a line with its photoId, followed by the photo."
)


def label_photos(photos: list[dict], photoshoot_id: str) -> list[dict]:
    content: list[dict[str, Any]] = [
        chat_client.text_part(PROMPT.format(rooms=", ".join(room.value for room in Room)))
    ]
    for photo in photos:
        content.append(chat_client.text_part(f"photoId: {photo['photoId']}"))
        content.append(chat_client.image_part(photo["jpegBytes"]))
    answer = chat_client.chat(
        "label_photos",
        get_settings().QUALITY_CHECK_MODEL,
        [{"role": "user", "content": content}],
        {"photoshootId": photoshoot_id},
        timeout_s=60,
        json_mode=True,
    )
    parsed = chat_client.parse_json(answer.content, answer.call_id)
    entries = parsed.get("labels") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        raise chat_client.bad_response(answer.call_id, "The answer had no labels list.")
    by_id: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("photoId"), str):
            raise chat_client.bad_response(answer.call_id, "A label had no photoId.")
        if entry["photoId"] in by_id:
            raise chat_client.bad_response(answer.call_id, "A photo was labelled twice.")
        by_id[entry["photoId"]] = entry
    result = []
    for photo in photos:
        entry = by_id.get(photo["photoId"])
        if entry is None:
            raise chat_client.bad_response(answer.call_id, "A photo was not labelled.")
        room = str(entry.get("room", "")).strip().lower()
        result.append(
            {
                "photoId": photo["photoId"],
                "room": Room(room) if room in Room.__members__ else Room.other,
                "subject": str(entry.get("subject", "")).strip(),
            }
        )
    return result
