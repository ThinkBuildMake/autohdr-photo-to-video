"""The labelPhotoshoot background job: read sizes, ask the labeller, write rooms and subjects."""

import logging
import tempfile
import threading
from pathlib import Path

from sqlalchemy import select, update

from app.config import get_settings
from app.db.base import session_scope
from app.files.service import get
from app.media.service import probe, thumbnail
from app.photoshoots.models import Photo, Photoshoot
from app.providers.interface import label_photos
from app.shared.enums import Room

log = logging.getLogger(__name__)

_threads: list[threading.Thread] = []
_threads_lock = threading.Lock()
_ROOMS = {room.value for room in Room}


def _set_status(photoshoot_id: str, status: str) -> None:
    with session_scope() as session:
        session.execute(
            update(Photoshoot).where(Photoshoot.id == photoshoot_id).values(status=status)
        )


def label_photoshoot(photoshoot_id: str) -> None:
    try:
        with session_scope() as session:
            rows = session.execute(
                select(Photo.id, Photo.file_key)
                .where(Photo.photoshoot_id == photoshoot_id, Photo.status == "uploaded")
                .order_by(Photo.position)
            ).all()
        sizes: dict[str, tuple[int, int]] = {}
        to_label: list[dict] = []
        long_side = get_settings().LABEL_IMAGE_LONG_SIDE
        for photo_id, file_key in rows:
            with tempfile.TemporaryDirectory() as folder:
                path = str(Path(folder) / "photo")
                get(file_key, path)
                info = probe(path)
                sizes[photo_id] = (info["width"], info["height"])
                jpeg = thumbnail(Path(path).read_bytes(), long_side)
            to_label.append({"photoId": photo_id, "jpegBytes": jpeg})
        labels = {item["photoId"]: item for item in label_photos(to_label, photoshoot_id)}
    except Exception as error:
        kind = getattr(error, "kind", type(error).__name__)
        log.warning("labelling failed for shoot %s: %s", photoshoot_id, kind)
        _set_status(photoshoot_id, "label_failed")
        return
    with session_scope() as session:
        for photo_id, (width, height) in sizes.items():
            label = labels.get(photo_id, {})
            room = label.get("room")
            session.execute(
                update(Photo)
                .where(Photo.id == photo_id)
                .values(
                    width=width,
                    height=height,
                    room=room if room in _ROOMS else Room.other.value,
                    subject=label.get("subject"),
                )
            )
        session.execute(
            update(Photoshoot).where(Photoshoot.id == photoshoot_id).values(status="ready")
        )


def start(photoshoot_id: str) -> threading.Thread:
    thread = threading.Thread(
        target=label_photoshoot, args=(photoshoot_id,), daemon=True, name=f"label-{photoshoot_id}"
    )
    with _threads_lock:
        _threads.append(thread)
    thread.start()
    return thread


def wait_idle(timeout: float = 10) -> None:
    with _threads_lock:
        threads = list(_threads)
        _threads.clear()
    for thread in threads:
        thread.join(timeout)


def relabel_interrupted() -> list[str]:
    with session_scope() as session:
        ids = list(session.scalars(select(Photoshoot.id).where(Photoshoot.status == "labelling")))
    for photoshoot_id in ids:
        start(photoshoot_id)
    return ids
