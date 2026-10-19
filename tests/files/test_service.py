import inspect
import logging
import os
from urllib.parse import urlsplit

from app.files import service


def test_service_exposes_the_five_operations():
    signatures = {
        name: str(inspect.signature(getattr(service, name)))
        for name in ("presign_upload", "presign_download", "put", "get", "head_object")
    }
    assert signatures == {
        "presign_upload": "(key: str, content_type: str, max_bytes: int) -> dict",
        "presign_download": (
            "(key: str, as_attachment: bool = False, filename: str | None = None) -> str"
        ),
        "put": "(key: str, path: str) -> None",
        "get": "(key: str, path: str) -> None",
        "head_object": "(key: str) -> dict | None",
    }


def test_service_exports_key_builders():
    for name in ("photo_key", "frame_key", "attempt_clip_key", "video_key", "song_key"):
        assert name in service.__all__
        assert callable(getattr(service, name))
    assert service.video_key("j1", 1) == "jobs/j1/video-v1.mp4"


def test_links_are_never_logged(bucket, caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    source = tmp_path / "clip.mp4"
    source.write_bytes(os.urandom(4096))
    key = service.video_key("j1", 1)

    upload = service.presign_upload(service.photo_key("s1", "p1", "jpg"), "image/jpeg", 1024)
    service.put(key, str(source))
    inline = service.presign_download(key)
    attachment = service.presign_download(key, as_attachment=True, filename="house.mp4")
    service.get(key, str(tmp_path / "back.mp4"))
    assert service.head_object(key) == {"sizeBytes": 4096}
    assert service.head_object("photoshoots/s1/p9.jpg") is None

    logged = caplog.text
    secrets = [inline, attachment, upload["url"] + upload["fields"]["key"]]
    secrets += [upload["fields"][name] for name in ("policy", "x-amz-signature")]
    secrets += [urlsplit(link).query for link in (inline, attachment)]
    for secret in secrets:
        assert secret not in logged
    assert "x-amz-signature" not in logged.lower()
    assert "X-Amz-Signature=" not in logged
