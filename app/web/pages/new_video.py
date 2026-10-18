"""Page: New video (GET /new)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.library import service
from app.web.templating import templates

router = APIRouter()


@router.get("/new", response_class=HTMLResponse)
def new_video_page(request: Request):
    return templates.TemplateResponse(
        request, "new_video.html", {"styles": service.list_styles(), "songs": service.list_songs()}
    )
