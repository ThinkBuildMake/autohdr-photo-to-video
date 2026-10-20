import io
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.config import reset_settings
from app.db.base import session_scope
from app.db.schema import init_db
from app.files.client import bucket_name, get_client
from app.files.service import put
from app.main import create_app
from app.photoshoots import labelling
from tests.support.fixtures import DEMO_AUTH, DEMO_PASSPHRASE


@pytest.fixture(autouse=True)
def _bucket(_isolated_environment, bucket):
    yield
    labelling.wait_idle()


@pytest.fixture
def client(_bucket, monkeypatch):
    monkeypatch.setenv("DEMO_PASSPHRASE", DEMO_PASSPHRASE)
    reset_settings()
    with TestClient(create_app()) as test_client:
        test_client.auth = DEMO_AUTH
        yield test_client


def jpeg_bytes(size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def put_bytes(key: str, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".jpg") as handle:
        handle.write(data)
        handle.flush()
        put(key, handle.name)


def object_keys() -> list[str]:
    found = get_client().list_objects_v2(Bucket=bucket_name())
    return [item["Key"] for item in found.get("Contents", [])]


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
                put_bytes(key, jpeg_bytes())
            photo_ids.append(photo_id)
    return shoot_id, photo_ids
