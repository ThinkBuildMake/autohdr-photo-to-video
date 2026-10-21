"""Page: Create a style (GET /styles/new)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.library import service
from app.photoshoots import service as photoshoots
from app.web.templating import templates

router = APIRouter()


@router.get("/styles/new", response_class=HTMLResponse)
def create_style_page(request: Request, styleId: str | None = None):
    return templates.TemplateResponse(
        request,
        "create_style.html",
        {
            "songs": service.list_songs(),
            "photoshoots": photoshoots.list_photoshoots(),
            "style": service.get_style(styleId) if styleId else None,
        },
    )
