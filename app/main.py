"""The web app: routes, pages and static files."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import access, errors, health
from app.comparison import routes as comparison_routes
from app.db.schema import init_db
from app.jobs import drafts
from app.jobs import routes as jobs_routes
from app.library import routes as library_routes
from app.photoshoots import routes as photoshoots_routes
from app.photoshoots import service as photoshoots_service
from app.web import pages

STATIC_DIR = Path(__file__).parent / "web" / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    photoshoots_service.on_app_start()
    drafts.on_app_start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    access.install(app)
    errors.install(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health.router)
    app.include_router(library_routes.router)
    app.include_router(photoshoots_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(comparison_routes.router)
    app.include_router(pages.router)
    return app


app = create_app()
