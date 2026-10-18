"""All Jobs routes under /api."""

from fastapi import APIRouter

from app.jobs.routes import drafts, edits, queue

router = APIRouter(prefix="/api")
router.include_router(drafts.router)
router.include_router(queue.router)
router.include_router(edits.router)
