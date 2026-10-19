"""Guard FR-3.6: a style holds text and a song only, never video taken from outside."""

import re
import sqlite3

import pytest

from app.config import get_settings
from app.db.schema import init_db
from tests.support.library_rows import add_song


def _style_body(song_id):
    return {
        "name": "Moody dusk",
        "authorName": "Sam",
        "styleText": "Dark and slow.",
        "songId": song_id,
    }


def test_styles_table_has_no_video_column():
    init_db()
    connection = sqlite3.connect(get_settings().DATABASE_PATH)
    try:
        columns = [row[1] for row in connection.execute("pragma table_info(styles)")]
    finally:
        connection.close()

    offending = [
        c
        for c in columns
        if re.search("video|frame|storyboard|clip", c) and c != "reference_job_id"
    ]
    assert offending == []


@pytest.mark.parametrize("field", ["videoUrl", "storyboard", "frames"])
def test_extra_creator_video_field_is_dropped(client, field):
    song_id = add_song()

    response = client.post("/api/styles", json={**_style_body(song_id), field: "x"})

    assert response.status_code == 201
    style = response.json()["style"]
    assert field not in style
    fetched = client.get(f"/api/styles/{style['id']}").json()
    assert field not in fetched["style"]
    assert field not in fetched


def test_update_with_video_field_is_refused(client):
    song_id = add_song()
    style_id = client.post("/api/styles", json=_style_body(song_id)).json()["style"]["id"]

    response = client.put(f"/api/styles/{style_id}", json={"videoUrl": "x"})

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_upload_of_only_a_video_has_no_valid_files(client):
    files = [{"name": "tour.mp4", "size": 1000, "type": "video/mp4"}]

    response = client.post("/api/photoshoots", json={"files": files})

    assert response.status_code == 400
    assert response.json()["error"] == "no_valid_files"


def test_upload_refuses_the_video_beside_a_photo(client):
    files = [
        {"name": "a.jpg", "size": 1000, "type": "image/jpeg"},
        {"name": "tour.mp4", "size": 1000, "type": "video/mp4"},
    ]

    body = client.post("/api/photoshoots", json={"files": files}).json()

    assert body["refused"] == [{"name": "tour.mp4", "reason": "wrong_type"}]
    assert [u["name"] for u in body["uploads"]] == ["a.jpg"]
