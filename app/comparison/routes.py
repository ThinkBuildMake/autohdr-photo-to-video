"""Comparison routes (ARCHITECTURE: Module: Comparison)."""

from fastapi import APIRouter

from app.comparison import service
from app.comparison.schemas import ReferenceRequest, Reproduction
from app.library.schemas import StyleOne

router = APIRouter(prefix="/api")


@router.post("/styles/{style_id}/reference")
def set_reference(style_id: str, body: ReferenceRequest) -> StyleOne:
    return StyleOne(style=service.set_reference(style_id, body.job_id))


@router.get("/styles/{style_id}/reproductions/{job_id}")
def get_reproduction(style_id: str, job_id: str) -> Reproduction:
    return service.get_reproduction(style_id, job_id)
