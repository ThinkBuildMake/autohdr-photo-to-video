"""All pages."""

from fastapi import APIRouter

from app.web.pages import compare, create_style, editor, job, jobs, new_video, styles

router = APIRouter()
for module in (styles, new_video, jobs, job, editor, create_style, compare):
    router.include_router(module.router)
