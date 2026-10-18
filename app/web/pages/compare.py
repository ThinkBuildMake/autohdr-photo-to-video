"""Page: a style's reproductions beside its reference (GET /styles/{style_id}/reproductions)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.errors import AppError
from app.library import service
from app.web.templating import templates

router = APIRouter()


@router.get("/styles/{style_id}/reproductions", response_class=HTMLResponse)
def compare_page(request: Request, style_id: str):
    try:
        style = service.get_style(style_id)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "compare.html",
            {"style": None, "error": exc.message},
            status_code=exc.status_code,
        )
    return templates.TemplateResponse(request, "compare.html", {"style": style, "error": None})
