import base64
import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.errors import AppError
from app.files.service import head_object
from app.photoshoots import labelling, service
from app.photoshoots.schemas import UploadFile, UploadRequest
from tests.photoshoots.conftest import jpeg_bytes, object_keys, put_bytes, write_jpegs

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _database():
    init_db()


def _req(files):
    return UploadRequest(files=[UploadFile(name=n, size=s, type=t) for n, s, t in files])


def test_de2_size_boundary():
    ok = service.create_upload(_req([("a.jpg", 26_214_400, "image/jpeg")]))
    assert len(ok.uploads) == 1
    with pytest.raises(AppError) as error:
        service.create_upload(_req([("b.jpg", 26_214_401, "image/jpeg")]))
    assert error.value.code == "no_valid_files"


def test_de2_count_boundary():
    files = [(f"{i}.jpg", 10, "image/jpeg") for i in range(40)]
    assert len(service.create_upload(_req(files)).uploads) == 40
    with pytest.raises(AppError) as error:
        service.create_upload(_req(files + [("x.jpg", 10, "image/jpeg")]))
    assert error.value.code == "too_many_files"


def test_de2_gif_refused_and_presign_arguments():
    body = service.create_upload(_req([("a.gif", 10, "image/gif"), ("b.png", 10, "image/png")]))
    assert [r.reason for r in body.refused] == ["wrong_type"]
    policy = json.loads(base64.b64decode(body.uploads[0].fields["policy"]))
    assert {"Content-Type": "image/png"} in policy["conditions"]
    assert ["content-length-range", 1, 26_214_400] in policy["conditions"]


def test_de2_complete_deletes_oversized_object():
    body = service.create_upload(_req([("a.jpg", 100, "image/jpeg")]))
    key = body.uploads[0].fields["key"]
    put_bytes(key, b"x" * 26_214_401)
    done = service.complete_upload(body.photoshoot_id)
    assert head_object(key) is None
    assert done.photos[0].status == "too_large"


def test_de2_import_skips_big_and_gif(tmp_path):
    paths = write_jpegs(tmp_path, 1)
    big = tmp_path / "big.jpg"
    big.write_bytes(b"x" * 26_214_401)
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"GIF89a")
    shoot_id = service.import_photoshoot([*paths, str(big), str(gif)], "S")
    assert len(service.get_photoshoot(shoot_id).photos) == 1
    labelling.wait_idle()


def test_fr36_video_refused_on_upload():
    body = service.create_upload(_req([("tour.mp4", 10, "video/mp4"), ("a.jpg", 10, "image/jpeg")]))
    assert [(r.name, r.reason) for r in body.refused] == [("tour.mp4", "wrong_type")]


def test_fr36_import_stores_no_video(tmp_path):
    video = tmp_path / "tour.mp4"
    video.write_bytes(b"\0" * 100)
    paths = [*write_jpegs(tmp_path, 1), str(video)]
    shoot_id = service.import_photoshoot(paths, "S")
    assert not any(key.endswith(".mp4") for key in object_keys())
    assert [p.original_name for p in service.get_photoshoot(shoot_id).photos] == ["photo-1.jpg"]
    labelling.wait_idle()


def test_fr36_photos_table_has_no_video_columns(client):
    with session_scope() as session:
        columns = [row[1] for row in session.execute(text("pragma table_info(photos)"))]
    assert not [c for c in columns if any(w in c for w in ("video", "frame", "storyboard", "clip"))]


def _images():
    out = subprocess.run(
        ["find", str(REPO), "-type", "f", "(", "-name", "*.jpg", "-o", "-name", "*.jpeg",
         "-o", "-name", "*.png", ")", "-not", "-path", "*/.git/*", "-not", "-path", "*/.venv/*",
         "-not", "-path", "*/node_modules/*"],
        capture_output=True,
        text=True,
        check=True,
    )  # fmt: skip
    return set(out.stdout.split())


def test_gc9_no_photo_written_to_repo(tmp_path):
    before = _images()
    body = service.create_upload(_req([("a.jpg", 10, "image/jpeg")]))
    put_bytes(body.uploads[0].fields["key"], jpeg_bytes())
    service.complete_upload(body.photoshoot_id)
    service.import_photoshoot(write_jpegs(tmp_path, 2), "S")
    labelling.wait_idle()
    assert _images() == before
