"""One JSON error format: {"error": snake_case_code, "message": text}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message})


def _app_error(_request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for item in exc.errors():
        where = ".".join(str(p) for p in item["loc"][1:]) or str(item["loc"][0])
        parts.append(f"{where}: {item['msg']}")
    return error_response(400, "invalid_request", "; ".join(parts) or "The request is invalid.")


def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code)
    code = code or f"http_{exc.status_code}"
    response = error_response(exc.status_code, code, str(exc.detail) or code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


def install(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
