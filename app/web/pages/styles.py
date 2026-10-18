"""Page: Styles (GET /)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.library import service
from app.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def styles_page(request: Request):
    return templates.TemplateResponse(request, "styles.html", {"styles": service.list_styles()})
