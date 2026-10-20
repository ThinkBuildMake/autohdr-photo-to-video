import os
from urllib.parse import urlsplit

import requests

from app.files.client import bucket_name, get_client
from app.files.downloads import presign_download
from app.files.keys import attempt_clip_key
from app.files.objects import delete_object, get, put
from app.files.uploads import head_object

THREE_MIB = 3 * 1024 * 1024


def make_clip(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(os.urandom(THREE_MIB))
    return source


def test_bucket_is_private(bucket, tmp_path):
    key = attempt_clip_key("j1", 1, 0, 1)
    put(key, str(make_clip(tmp_path)))
    parts = urlsplit(presign_download(key))
    plain_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    response = requests.get(plain_url, timeout=10)
    assert response.status_code == 403
    assert len(response.content) < 1024


def test_put_get_round_trip(bucket, tmp_path):
    key = attempt_clip_key("j1", 1, 0, 1)
    assert key == "jobs/j1/shots/1/r0/a1.mp4"
    source = make_clip(tmp_path)
    put(key, str(source))
    assert head_object(key) == {"sizeBytes": THREE_MIB}
    out = tmp_path / "back.mp4"
    get(key, str(out))
    assert out.read_bytes() == source.read_bytes()


def test_delete_object_removes_the_key(bucket, tmp_path):
    key = attempt_clip_key("j1", 1, 0, 1)
    put(key, str(make_clip(tmp_path)))
    delete_object(key)
    assert head_object(key) is None


def test_put_sets_content_type_and_no_acl(bucket, tmp_path):
    key = attempt_clip_key("j1", 1, 0, 1)
    put(key, str(make_clip(tmp_path)))
    client = get_client()
    assert client.head_object(Bucket=bucket_name(), Key=key)["ContentType"] == "video/mp4"
    grants = client.get_object_acl(Bucket=bucket_name(), Key=key)["Grants"]
    assert all(grant["Grantee"].get("URI") is None for grant in grants)
