import io

import pytest
from PIL import Image

from app.db.base import session_scope
from app.db.schema import init_db
from app.errors import AppError
from app.photoshoots import service
from app.photoshoots.models import Photo
from tests.photoshoots.conftest import object_keys, put_bytes, seed_shoot


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_worker_reads_original_uploaded_bytes(fmt):
    shoot, (photo,) = seed_shoot(["uploaded"])
    key = f"photoshoots/{shoot}/{photo}.jpg"
    buffer = io.BytesIO()
    Image.new("RGB", (93, 61), "orange").save(buffer, fmt)
    original = buffer.getvalue()
    with session_scope() as session:
        row = session.get(Photo, photo)
        row.content_type = "image/png" if fmt == "PNG" else "image/jpeg"
        row.size_bytes = len(original)
    put_bytes(key, original)
    before = object_keys()

    assert service.photo_bytes(shoot, photo) == original
    assert service.photo_bytes(shoot, photo) == original
    assert object_keys() == before


@pytest.mark.parametrize("status", ["awaiting_upload", "missing", "too_large"])
def test_worker_rejects_unuploaded_photo(status):
    shoot, (photo,) = seed_shoot([status])
    with pytest.raises(AppError) as caught:
        service.photo_bytes(shoot, photo)
    assert (caught.value.status_code, caught.value.code) == (400, "photo_not_uploaded")


def test_worker_rejects_missing_shoot():
    init_db()
    with pytest.raises(service.PhotoshootNotFound):
        service.photo_bytes("absent", "absent")


@pytest.mark.parametrize("other_shoot", [False, True])
def test_worker_rejects_missing_or_cross_shoot_photo(other_shoot):
    shoot, _ = seed_shoot(["uploaded"])
    photo = seed_shoot(["uploaded"])[1][0] if other_shoot else "absent"
    with pytest.raises(AppError) as caught:
        service.photo_bytes(shoot, photo)
    assert (caught.value.status_code, caught.value.code) == (404, "photo_not_found")
