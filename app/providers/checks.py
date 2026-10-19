"""checkEdit and checkClip: the model lists what differs, the app decides (VR-5)."""

import base64
import os
from typing import Any

from app.config import get_settings
from app.providers import chat as chat_client
from app.shared.types import ClipCheck, EditCheck

ARCHITECTURE_WORDS = (
    "wall",
    "window",
    "door",
    "fixture",
    "cabinet",
    "counter",
    "vent",
    "outlet",
    "light fixture",
    "fireplace",
    "stair",
    "ceiling",
    "floor",
    "sink",
    "toilet",
    "shower",
    "bath",
    "mirror",
    "room",
)

EDIT_PROMPT = (
    "You compare two real-estate photos: the ORIGINAL (first image) and the EDITED one (second "
    "image). List every object that was added, removed or changed in the edited photo, "
    "ignoring light, colour and exposure. Say whether any architectural or interior feature "
    "(walls, windows, doors, fixtures, cabinets, counters, floors, ceilings) changed. "
    "Answer with JSON only: "
    '{"addedObjects": [string], "removedObjects": [string], "changedObjects": [string], '
    '"architectureChanged": boolean, "notes": string}.'
)

CLIP_PROMPT = (
    "You check an AI-generated video clip made from a real-estate photo. The first image is the "
    "SOURCE photo; then comes the clip, then frames sampled from the clip. Give aiScore (0 = "
    "looks real, 1 = obviously AI-made), matchScore (0 = a different place, 1 = the same "
    "place as the source), peopleCount (people visible, also in reflections), and the lists of "
    "objects added, removed or changed compared with the source. "
    "Answer with JSON only: "
    '{"aiScore": number, "matchScore": number, "peopleCount": integer, "addedObjects": [string], '
    '"removedObjects": [string], "changedObjects": [string], "notes": string}.'
)


def _list(data: dict, key: str, call_id: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise chat_client.bad_response(call_id, f"{key} was not a list of text.")
    return value


def _number(data: dict, key: str, call_id: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise chat_client.bad_response(call_id, f"{key} was not a number.")
    return float(value)


def _object(answer: chat_client.ChatAnswer) -> dict:
    parsed = chat_client.parse_json(answer.content, answer.call_id)
    if not isinstance(parsed, dict):
        raise chat_client.bad_response(answer.call_id, "The answer was not a JSON object.")
    return parsed


def _notes(data: dict, call_id: str) -> str:
    notes = data.get("notes")
    if not isinstance(notes, str):
        raise chat_client.bad_response(call_id, "notes was not text.")
    return notes.strip()


def _append_unmentioned(notes: str, lists: dict[str, list[str]]) -> str:
    lowered = notes.lower()
    extra = [
        f"{label}: {item}"
        for label, items in lists.items()
        for item in items
        if item.lower() not in lowered
    ]
    return "; ".join([part for part in [notes, *extra] if part])


def _touches_architecture(items: list[str]) -> bool:
    return any(word in item.lower() for item in items for word in ARCHITECTURE_WORDS)


def check_edit(original_jpeg: bytes, edited_jpeg: bytes, ids: dict[str, Any]) -> EditCheck:
    content = [
        chat_client.text_part(EDIT_PROMPT),
        chat_client.image_part(original_jpeg),
        chat_client.image_part(edited_jpeg),
    ]
    answer = chat_client.chat(
        "check_edit",
        get_settings().QUALITY_CHECK_MODEL,
        [{"role": "user", "content": content}],
        ids,
        timeout_s=60,
        json_mode=True,
    )
    data = _object(answer)
    added = _list(data, "addedObjects", answer.call_id)
    removed = _list(data, "removedObjects", answer.call_id)
    changed = _list(data, "changedObjects", answer.call_id)
    flag = data.get("architectureChanged")
    if not isinstance(flag, bool):
        raise chat_client.bad_response(answer.call_id, "architectureChanged was not true or false.")
    notes = _append_unmentioned(
        _notes(data, answer.call_id),
        {"removed": removed, "added": added, "changed": changed},
    )
    return EditCheck(
        added_objects=added,
        removed_objects=removed,
        changed_objects=changed,
        architecture_changed=flag or _touches_architecture(added + removed + changed),
        notes=notes,
    )


def check_clip(
    clip_path: str, frames: list[bytes], source_jpeg: bytes, ids: dict[str, Any]
) -> ClipCheck:
    content = [chat_client.text_part(CLIP_PROMPT), chat_client.image_part(source_jpeg)]
    if os.path.exists(clip_path):
        with open(clip_path, "rb") as clip_file:
            encoded = base64.b64encode(clip_file.read()).decode("ascii")
        content.append(
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{encoded}"}}
        )
    content.extend(chat_client.image_part(frame) for frame in frames)
    answer = chat_client.chat(
        "check_clip",
        get_settings().QUALITY_CHECK_MODEL,
        [{"role": "user", "content": content}],
        ids,
        timeout_s=90,
        json_mode=True,
    )
    data = _object(answer)
    ai_score = _number(data, "aiScore", answer.call_id)
    match_score = _number(data, "matchScore", answer.call_id)
    people = _number(data, "peopleCount", answer.call_id)
    if people != int(people) or people < 0:
        raise chat_client.bad_response(answer.call_id, "peopleCount was not a whole number.")
    people_count = int(people)
    added = _list(data, "addedObjects", answer.call_id)
    removed = _list(data, "removedObjects", answer.call_id)
    changed = _list(data, "changedObjects", answer.call_id)
    notes = _append_unmentioned(
        _notes(data, answer.call_id),
        {"removed": removed, "added": added, "changed": changed},
    )
    if people_count > 0 and "person" not in notes.lower() and "people" not in notes.lower():
        notes = f"{people_count} person(s) appear in the clip. {notes}".strip()
    settings = get_settings()
    passed = (
        ai_score <= settings.CHECK_MAX_AI_SCORE
        and match_score >= settings.CHECK_MIN_MATCH_SCORE
        and people_count == 0
        and not (added or removed or changed)
    )
    return ClipCheck(
        ai_score=ai_score,
        match_score=match_score,
        people_count=people_count,
        added_objects=added,
        removed_objects=removed,
        changed_objects=changed,
        passed=passed,
        notes=notes,
    )
