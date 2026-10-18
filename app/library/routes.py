"""Library routes (ARCHITECTURE: Module: Library)."""

from fastapi import APIRouter

from app.library import service
from app.library.schemas import (
    SongList,
    StyleCreate,
    StyleDetail,
    StyleList,
    StyleOne,
    StyleUpdate,
)

router = APIRouter(prefix="/api")


@router.get("/styles")
def list_styles() -> StyleList:
    return StyleList(styles=service.list_styles())


@router.get("/styles/{style_id}")
def get_style(style_id: str) -> StyleDetail:
    style = service.get_style(style_id)
    return StyleDetail(style=style, reference_video_url=service.reference_video_url(style_id))


@router.get("/songs")
def list_songs() -> SongList:
    return SongList(songs=service.list_songs())


@router.post("/styles", status_code=201)
def create_style(body: StyleCreate) -> StyleOne:
    return StyleOne(style=service.create_style(body))


@router.put("/styles/{style_id}")
def update_style(style_id: str, body: StyleUpdate) -> StyleOne:
    return StyleOne(style=service.update_style(style_id, body))
