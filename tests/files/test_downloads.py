from urllib.parse import parse_qs, urlsplit

import requests

from app.files.client import bucket_name, get_client
from app.files.downloads import presign_download
from app.files.keys import video_key

VIDEO = b"not really a video" * 100


def put_video(key: str) -> None:
    get_client().put_object(Bucket=bucket_name(), Key=key, Body=VIDEO)


def test_download_link_works_for_an_hour(bucket):
    key = video_key("j1", 1)
    assert key == "jobs/j1/video-v1.mp4"
    put_video(key)
    link = presign_download(key)
    response = requests.get(link, timeout=10)
    assert response.status_code == 200
    assert response.content == VIDEO
    assert parse_qs(urlsplit(link).query)["X-Amz-Expires"] == ["3600"]


def test_download_as_attachment(bucket):
    key = video_key("j1", 1)
    put_video(key)
    response = requests.get(
        presign_download(key, as_attachment=True, filename="house.mp4"), timeout=10
    )
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="house.mp4"'
    plain = requests.get(presign_download(key), timeout=10)
    assert "attachment" not in plain.headers.get("Content-Disposition", "")


def test_attachment_name_defaults_to_key_basename_and_is_sanitised(bucket):
    key = video_key("j1", 1)
    put_video(key)
    default = requests.get(presign_download(key, as_attachment=True), timeout=10)
    assert default.headers["Content-Disposition"] == 'attachment; filename="video-v1.mp4"'
    odd = requests.get(
        presign_download(key, as_attachment=True, filename='../a"b/house.mp4'), timeout=10
    )
    assert odd.headers["Content-Disposition"] == 'attachment; filename="..abhouse.mp4"'
