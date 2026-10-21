"""Photoshoots module interface: upload, complete, read, list, import and relabel on start."""

import logging
import os
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select, update

from app.config import get_settings
from app.db.base import session_scope
from app.errors import AppError
from app.files import service as files
from app.media import service as media
from app.photoshoots import labelling
from app.photoshoots.models import Photo as PhotoRow
from app.photoshoots.models import Photoshoot
from app.photoshoots.schemas import (
    CompletedPhotoshoot,
    PhotoshootDetail,
    RefusedFile,
    UploadRequest,
    UploadResponse,
    UploadTicket,
)
from app.shared.types import Photo

log = logging.getLogger(__name__)

MAX_FILES = 40
MAX_BYTES = 25 * 1024 * 1024
ALLOWED_TYPES = ("image/jpeg", "image/png")
_SUFFIX_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class PhotoshootNotFound(AppError):
    def __init__(self, photoshoot_id: str):
        super().__init__(404, "photoshoot_not_found", f"No photoshoot with id {photoshoot_id}.")


def _too_many() -> AppError:
    return AppError(400, "too_many_files", f"At most {MAX_FILES} photos per photoshoot.")


def _no_valid() -> AppError:
    return AppError(400, "no_valid_files", "None of the files can be used.")


def _classify(content_type: str, size: int) -> str | None:
    if content_type not in ALLOWED_TYPES:
        return "wrong_type"
    if size > MAX_BYTES:
        return "too_large"
    return None


def _insert_shoot(label: str | None, files: list[tuple[str, str, int]]) -> tuple[str, list[dict]]:
    """Insert a photoshoot and one photo per (name, content_type, size). Returns id and rows."""
    shoot_id = str(uuid.uuid4())
    rows = []
    with session_scope() as session:
        session.add(Photoshoot(id=shoot_id, label=label, status="awaiting_upload"))
        session.flush()
        for position, (name, content_type, size) in enumerate(files, start=1):
            photo_id = str(uuid.uuid4())
            extension = "png" if content_type == "image/png" else "jpg"
            key = f"photoshoots/{shoot_id}/{photo_id}.{extension}"
            session.add(
                PhotoRow(
                    id=photo_id,
                    photoshoot_id=shoot_id,
                    position=position,
                    original_name=name,
                    content_type=content_type,
                    size_bytes=size,
                    file_key=key,
                    status="awaiting_upload",
                )
            )
            rows.append(
                {"photo_id": photo_id, "name": name, "content_type": content_type, "key": key}
            )
    return shoot_id, rows


def create_upload(body: UploadRequest) -> UploadResponse:
    if len(body.files) > MAX_FILES:
        raise _too_many()
    accepted: list[tuple[str, str, int]] = []
    refused: list[RefusedFile] = []
    for file in body.files:
        reason = _classify(file.type, file.size)
        if reason:
            refused.append(RefusedFile(name=file.name, reason=reason))
        else:
            accepted.append((file.name, file.type, file.size))
    if not accepted:
        raise _no_valid()
    shoot_id, rows = _insert_shoot(body.label, accepted)
    uploads = []
    for row in rows:
        form = files.presign_upload(row["key"], row["content_type"], MAX_BYTES)
        uploads.append(
            UploadTicket(
                photo_id=row["photo_id"], name=row["name"], url=form["url"], fields=form["fields"]
            )
        )
    return UploadResponse(photoshoot_id=shoot_id, uploads=uploads, refused=refused)


def _to_photo(row: PhotoRow) -> Photo:
    return Photo(
        id=row.id,
        position=row.position,
        original_name=row.original_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        status=row.status,
        room=row.room,
        subject=row.subject,
        thumb_url=files.presign_download(row.file_key),
    )


def _read(photoshoot_id: str, only_uploaded: bool = False) -> tuple[Photoshoot, list[Photo]]:
    with session_scope() as session:
        shoot = session.get(Photoshoot, photoshoot_id)
        if shoot is None:
            raise PhotoshootNotFound(photoshoot_id)
        query = select(PhotoRow).where(PhotoRow.photoshoot_id == photoshoot_id)
        if only_uploaded:
            query = query.where(PhotoRow.status == "uploaded")
        photos = [_to_photo(row) for row in session.scalars(query.order_by(PhotoRow.position))]
        session.expunge(shoot)
    return shoot, photos


def complete_upload(photoshoot_id: str) -> CompletedPhotoshoot:
    with session_scope() as session:
        shoot = session.get(Photoshoot, photoshoot_id)
        if shoot is None:
            raise PhotoshootNotFound(photoshoot_id)
        pending = session.execute(
            select(PhotoRow.id, PhotoRow.file_key)
            .where(
                PhotoRow.photoshoot_id == photoshoot_id,
                PhotoRow.status.in_(("awaiting_upload", "missing")),
            )
            .order_by(PhotoRow.position)
        ).all()
    outcomes: dict[str, str] = {}
    for photo_id, file_key in pending:
        head = files.head_object(file_key)
        if head is None:
            outcomes[photo_id] = "missing"
        elif head["sizeBytes"] > MAX_BYTES:
            files.delete_object(file_key)
            outcomes[photo_id] = "too_large"
        else:
            outcomes[photo_id] = "uploaded"
    with session_scope() as session:
        for photo_id, status in outcomes.items():
            session.execute(update(PhotoRow).where(PhotoRow.id == photo_id).values(status=status))
        uploaded = session.scalars(
            select(PhotoRow.id).where(
                PhotoRow.photoshoot_id == photoshoot_id, PhotoRow.status == "uploaded"
            )
        ).first()
        start_labelling = False
        if uploaded is not None:
            claimed = session.execute(
                update(Photoshoot)
                .where(
                    Photoshoot.id == photoshoot_id,
                    Photoshoot.status.not_in(("ready", "labelling")),
                )
                .values(status="labelling")
            )
            start_labelling = claimed.rowcount == 1
    shoot, photos = _read(photoshoot_id)
    if start_labelling:
        labelling.start(photoshoot_id)
    return CompletedPhotoshoot(id=photoshoot_id, status=shoot.status, photos=photos)


def get_photoshoot(photoshoot_id: str) -> PhotoshootDetail:
    shoot, photos = _read(photoshoot_id)
    return PhotoshootDetail(id=shoot.id, label=shoot.label, status=shoot.status, photos=photos)


def list_photos(photoshoot_id: str) -> list[Photo]:
    return _read(photoshoot_id, only_uploaded=True)[1]


def planner_photos(photoshoot_id: str) -> list[dict]:
    """Uploaded photos in upload order, as the planner's {photoId, room, subject, jpegBytes}."""
    with session_scope() as session:
        if session.get(Photoshoot, photoshoot_id) is None:
            raise PhotoshootNotFound(photoshoot_id)
        rows = session.execute(
            select(PhotoRow.id, PhotoRow.file_key, PhotoRow.room, PhotoRow.subject)
            .where(PhotoRow.photoshoot_id == photoshoot_id, PhotoRow.status == "uploaded")
            .order_by(PhotoRow.position)
        ).all()
    long_side = get_settings().LABEL_IMAGE_LONG_SIDE
    photos = []
    for photo_id, file_key, room, subject in rows:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "photo"
            files.get(file_key, str(path))
            jpeg = media.thumbnail(path.read_bytes(), long_side)
        photos.append({"photoId": photo_id, "room": room, "subject": subject, "jpegBytes": jpeg})
    return photos


def list_photoshoots() -> list[tuple[str, str | None]]:
    """(id, label) of every shoot whose upload finished, newest first: the shoot pickers."""
    with session_scope() as session:
        return session.execute(
            select(Photoshoot.id, Photoshoot.label)
            .where(Photoshoot.status != "awaiting_upload")
            .order_by(Photoshoot.created_at.desc())
        ).all()


def import_photoshoot(paths: Sequence[str], label: str) -> str:
    if len(paths) > MAX_FILES:
        raise _too_many()
    accepted: list[tuple[str, str, int]] = []
    sources: list[str] = []
    for path in paths:
        name = Path(path).name
        content_type = _SUFFIX_TYPES.get(Path(path).suffix.lower(), "")
        size = os.path.getsize(path)
        reason = _classify(content_type, size)
        if reason:
            log.info("import skipped %s: %s", name, reason)
            continue
        accepted.append((name, content_type, size))
        sources.append(path)
    if not accepted:
        raise _no_valid()
    shoot_id, rows = _insert_shoot(label, accepted)
    for row, path in zip(rows, sources, strict=True):
        files.put(row["key"], path)
    complete_upload(shoot_id)
    return shoot_id


def on_app_start() -> None:
    labelling.relabel_interrupted()
