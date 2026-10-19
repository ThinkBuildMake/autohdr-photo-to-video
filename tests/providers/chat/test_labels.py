import json

import pytest

from app.providers import labels
from app.providers.errors import ProviderError
from app.shared.enums import Room

LABELS = {
    "labels": [
        {"photoId": "p1", "room": "kitchen", "subject": "white island with stools"},
        {"photoId": "p2", "room": "bedroom", "subject": "queen bed under window"},
    ]
}


def photos(synthetic_jpeg):
    return [
        {"photoId": "p1", "jpegBytes": synthetic_jpeg("tan", "kitchen")},
        {"photoId": "p2", "jpegBytes": synthetic_jpeg("navy", "bedroom")},
    ]


def test_labels_kitchen_and_bedroom(openrouter, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(json=chat_answer(json.dumps(LABELS)))

    result = labels.label_photos(photos(synthetic_jpeg), "ps-1")

    assert [r["photoId"] for r in result] == ["p1", "p2"]
    assert result[0]["room"] == Room.kitchen and result[0]["subject"]
    assert result[1]["room"] == Room.bedroom and result[1]["subject"]
    body = openrouter.body()
    parts = body["messages"][0]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 2
    assert body["model"] == "google/gemini-3.8-flash"
    (row,) = rows()
    assert (row.kind, row.photoshoot_id, row.status) == ("label_photos", "ps-1", "ok")


def test_unknown_room_becomes_other(openrouter, chat_answer, synthetic_jpeg):
    data = {"labels": [{**LABELS["labels"][0], "room": "garage"}, LABELS["labels"][1]]}
    openrouter.answer(json=chat_answer(json.dumps(data)))
    assert labels.label_photos(photos(synthetic_jpeg), "ps-1")[0]["room"] == Room.other


def test_missing_photo_is_bad_response(openrouter, chat_answer, synthetic_jpeg, rows):
    openrouter.answer(json=chat_answer(json.dumps({"labels": LABELS["labels"][:1]})))

    with pytest.raises(ProviderError) as caught:
        labels.label_photos(photos(synthetic_jpeg), "ps-1")

    assert caught.value.kind == "bad_response"
    (row,) = rows()
    assert row.status == "error" and row.error_kind == "bad_response"


@pytest.mark.live
def test_live_label_photos(live, synthetic_jpeg):
    result = labels.label_photos(
        [
            {"photoId": "k", "jpegBytes": synthetic_jpeg("tan", "kitchen island and stools")},
            {"photoId": "b", "jpegBytes": synthetic_jpeg("navy", "bedroom with a bed")},
        ],
        "ps-1",
    )
    assert len(result) == 2
    assert all(isinstance(r["room"], Room) for r in result)
