"""Photoshoots routes (ARCHITECTURE: Module: Photoshoots)."""

from fastapi import APIRouter

from app.photoshoots import service
from app.photoshoots.schemas import (
    CompleteResponse,
    PhotoshootList,
    PhotoshootResponse,
    PhotoshootSummary,
    UploadRequest,
    UploadResponse,
)

router = APIRouter(prefix="/api")


@router.post("/photoshoots", status_code=201)
def create_upload(body: UploadRequest) -> UploadResponse:
    return service.create_upload(body)


@router.get("/photoshoots")
def list_photoshoots() -> PhotoshootList:
    return PhotoshootList(
        photoshoots=[
            PhotoshootSummary(id=shoot_id, label=label)
            for shoot_id, label in service.list_photoshoots()
        ]
    )


@router.post("/photoshoots/{photoshoot_id}/complete", status_code=202)
def complete_upload(photoshoot_id: str) -> CompleteResponse:
    return CompleteResponse(photoshoot=service.complete_upload(photoshoot_id))


@router.get("/photoshoots/{photoshoot_id}")
def get_photoshoot(photoshoot_id: str) -> PhotoshootResponse:
    return PhotoshootResponse(photoshoot=service.get_photoshoot(photoshoot_id))
