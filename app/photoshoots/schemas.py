"""Photoshoots request and response shapes."""

from app.shared.types import CamelModel, Photo


class UploadFile(CamelModel):
    name: str
    size: int
    type: str


class UploadRequest(CamelModel):
    label: str | None = None
    files: list[UploadFile]


class UploadTicket(CamelModel):
    photo_id: str
    name: str
    url: str
    fields: dict[str, str]


class RefusedFile(CamelModel):
    name: str
    reason: str


class UploadResponse(CamelModel):
    photoshoot_id: str
    uploads: list[UploadTicket]
    refused: list[RefusedFile]


class CompletedPhotoshoot(CamelModel):
    id: str
    status: str
    photos: list[Photo]


class CompleteResponse(CamelModel):
    photoshoot: CompletedPhotoshoot


class PhotoshootDetail(CamelModel):
    id: str
    label: str | None
    status: str
    photos: list[Photo]


class PhotoshootResponse(CamelModel):
    photoshoot: PhotoshootDetail
