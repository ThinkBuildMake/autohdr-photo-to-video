import base64
import io
import json
from datetime import UTC, datetime, timedelta

import requests
from PIL import Image

from app.files.keys import (
    attempt_clip_key,
    frame_key,
    photo_key,
    song_key,
    video_key,
)
from app.files.uploads import head_object, presign_upload

MAX_BYTES = 26214400
ONE_MIB = 1048576


def make_jpeg(size: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(buffer, "JPEG")
    data = buffer.getvalue()
    return data + b"\0" * (size - len(data))


def post_form(form, data: bytes, name: str = "p1.jpg", fields: dict | None = None):
    return requests.post(
        form["url"],
        data=fields if fields is not None else form["fields"],
        files={"file": (name, data)},
        timeout=10,
    )


def presign_at(monkeypatch, age: timedelta, key: str):
    then = datetime.now(UTC) - age
    with monkeypatch.context() as patch:
        patch.setattr("botocore.signers.get_current_datetime", lambda: then)
        return presign_upload(key, "image/jpeg", MAX_BYTES)


def test_key_layout():
    assert photo_key("s1", "p1", "jpg") == "photoshoots/s1/p1.jpg"
    assert photo_key("s1", "p1", "png") == "photoshoots/s1/p1.png"
    assert frame_key("j1", 1, 0, "cropped") == "jobs/j1/shots/1/r0/cropped.jpg"
    assert frame_key("j1", 2, 1, "edited") == "jobs/j1/shots/2/r1/edited.jpg"
    assert attempt_clip_key("j1", 1, 0, 1) == "jobs/j1/shots/1/r0/a1.mp4"
    assert video_key("j1", 1) == "jobs/j1/video-v1.mp4"
    assert song_key("x", "mp3") == "songs/x.mp3"


def test_upload_link_accepts_small_file(bucket):
    key = photo_key("s1", "p1", "jpg")
    form = presign_upload(key, "image/jpeg", MAX_BYTES)

    response = post_form(form, make_jpeg(ONE_MIB))

    assert response.status_code == 204
    assert head_object(key) == {"sizeBytes": ONE_MIB}


def test_upload_link_expires(bucket, monkeypatch):
    key = photo_key("s1", "p1", "jpg")
    expired = presign_at(monkeypatch, timedelta(minutes=16), key)

    response = post_form(expired, make_jpeg(2048))

    assert response.status_code == 403
    assert head_object(key) is None


def test_upload_link_made_14_minutes_ago_still_works(bucket, monkeypatch):
    key = photo_key("s1", "p1", "jpg")
    form = presign_at(monkeypatch, timedelta(minutes=14), key)

    assert post_form(form, make_jpeg(2048)).status_code == 204
    assert head_object(key) == {"sizeBytes": 2048}


def test_missing_object_is_none(bucket):
    assert head_object("photoshoots/s1/p9.jpg") is None


def test_upload_form_limits_size_and_type(bucket):
    key = photo_key("s1", "p1", "jpg")
    form = presign_upload(key, "image/jpeg", MAX_BYTES)
    policy = json.loads(base64.b64decode(form["fields"]["policy"]))

    assert ["content-length-range", 1, MAX_BYTES] in policy["conditions"]
    assert {"Content-Type": "image/jpeg"} in policy["conditions"]

    assert post_form(form, b"\0" * (MAX_BYTES + 1)).status_code == 403
    wrong_type = {**form["fields"], "Content-Type": "text/plain"}
    assert post_form(form, make_jpeg(2048), fields=wrong_type).status_code == 403
    assert post_form(form, b"").status_code == 403
    assert head_object(key) is None
