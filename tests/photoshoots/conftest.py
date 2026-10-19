import io
import uuid
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import text

from app.db.base import session_scope
from app.db.schema import init_db
from app.photoshoots import labelling, stubs
from tests.support.fixtures import client, live_server  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_bucket():
    stubs.BUCKET.clear()
    yield
    labelling.wait_idle()


def jpeg_bytes(size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def write_jpegs(folder, n) -> list[str]:
    paths = []
    for index in range(n):
        path = Path(folder) / f"photo-{index + 1}.jpg"
        path.write_bytes(jpeg_bytes())
        paths.append(str(path))
    return paths


def seed_shoot(statuses, shoot_status="labelling", label=None):
    init_db()
    shoot_id = str(uuid.uuid4())
    photo_ids = []
    with session_scope() as session:
        session.execute(
            text("insert into photoshoots (id, label, status) values (:i, :l, :s)"),
            {"i": shoot_id, "l": label, "s": shoot_status},
        )
        for position, status in enumerate(statuses, start=1):
            photo_id = str(uuid.uuid4())
            key = f"photoshoots/{shoot_id}/{photo_id}.jpg"
            session.execute(
                text(
                    "insert into photos (id, photoshoot_id, position, original_name, content_type,"
                    " size_bytes, file_key, status) values (:i, :s, :p, :n, 'image/jpeg', 1000,"
                    " :k, :st)"
                ),
                {
                    "i": photo_id,
                    "s": shoot_id,
                    "p": position,
                    "n": f"p{position}.jpg",
                    "k": key,
                    "st": status,
                },
            )
            if status == "uploaded":
                stubs.BUCKET[key] = jpeg_bytes()
            photo_ids.append(photo_id)
    return shoot_id, photo_ids
