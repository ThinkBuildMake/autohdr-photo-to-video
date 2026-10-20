"""Page: New video (GET /new, or /new?jobId= to check a draft's shot plan)."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.jobs.plan_rules import MOVEMENT_NAMES, MOVEMENTS
from app.library import service
from app.web.templating import templates

router = APIRouter()


@router.get("/new", response_class=HTMLResponse)
def new_video_page(request: Request, style_id: str | None = Query(None, alias="styleId")):
    styles = service.list_styles()
    songs = service.list_songs()
    return templates.TemplateResponse(
        request,
        "new_video.html",
        {
            "styles": styles,
            "selected": next((s for s in styles if s.id == style_id), None),
            "songs": [(song, service.song_preview_url(song.id)) for song in songs],
            "movement_names": MOVEMENT_NAMES,
            "movement_prompts": MOVEMENTS,
        },
    )
