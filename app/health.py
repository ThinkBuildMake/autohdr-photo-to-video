"""GET /healthz: 200 when the database opens. No passphrase."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.base import session_scope
from app.errors import error_response

router = APIRouter()


@router.get("/healthz")
def healthz() -> JSONResponse:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        return error_response(503, "database_unavailable", "The database could not be opened.")
    return JSONResponse({"status": "ok"})
