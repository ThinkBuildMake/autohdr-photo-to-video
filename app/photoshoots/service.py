"""Photoshoots module interface. Stub: classifies files, answers from stub data until S08."""

import uuid
from collections.abc import Sequence

from app.errors import AppError
from app.photoshoots import stubs
from app.photoshoots.schemas import (
    CompletedPhotoshoot,
    PhotoshootDetail,
    RefusedFile,
    UploadRequest,
    UploadResponse,
    UploadTicket,
)
from app.shared.types import Photo

MAX_FILES = 40
MAX_BYTES = 25 * 1024 * 1024
ALLOWED_TYPES = ("image/jpeg", "image/png")


class PhotoshootNotFound(AppError):
    def __init__(self, photoshoot_id: str):
        super().__init__(404, "photoshoot_not_found", f"No photoshoot with id {photoshoot_id}.")


def _require(photoshoot_id: str) -> None:
    if photoshoot_id != stubs.STUB_PHOTOSHOOT_ID:
        raise PhotoshootNotFound(photoshoot_id)


def create_upload(body: UploadRequest) -> UploadResponse:
    if len(body.files) > MAX_FILES:
        raise AppError(400, "too_many_files", f"At most {MAX_FILES} photos per photoshoot.")
    uploads: list[UploadTicket] = []
    refused: list[RefusedFile] = []
    for file in body.files:
        if file.type not in ALLOWED_TYPES:
            refused.append(RefusedFile(name=file.name, reason="wrong_type"))
        elif file.size > MAX_BYTES:
            refused.append(RefusedFile(name=file.name, reason="too_large"))
        else:
            photo_id = str(uuid.uuid4())
            uploads.append(
                UploadTicket(
                    photo_id=photo_id,
                    name=file.name,
                    url=f"/stub-upload/{photo_id}",
                    fields={"key": f"photoshoots/stub/{photo_id}"},
                )
            )
    if not uploads:
        raise AppError(400, "no_valid_files", "None of the files can be used.")
    return UploadResponse(photoshoot_id=stubs.STUB_PHOTOSHOOT_ID, uploads=uploads, refused=refused)


def complete_upload(photoshoot_id: str) -> CompletedPhotoshoot:
    _require(photoshoot_id)
    return CompletedPhotoshoot(id=photoshoot_id, status="labelling", photos=stubs.stub_photos())


def get_photoshoot(photoshoot_id: str) -> PhotoshootDetail:
    _require(photoshoot_id)
    return PhotoshootDetail(
        id=photoshoot_id, label=stubs.STUB_LABEL, status="ready", photos=stubs.stub_photos()
    )


def list_photos(photoshoot_id: str) -> list[Photo]:
    _require(photoshoot_id)
    return stubs.stub_photos()


def import_photoshoot(paths: Sequence[str], label: str) -> str:
    return stubs.STUB_PHOTOSHOOT_ID


def on_app_start() -> None:
    """S08 re-starts labelling for any shoot left labelling."""
    return None
