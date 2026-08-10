from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def _response(code: str, message: str, detail: Any = None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            # Keep detail for compatibility with the existing frontend clients.
            "detail": jsonable_encoder(detail),
        },
    )


async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    # detail defaults to message so existing clients that read response.detail keep working.
    detail = exc.message if exc.detail is None else exc.detail
    return _response(exc.code, exc.message, detail, exc.status_code)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    return _response(f"HTTP_{exc.status_code}", message, detail, exc.status_code)


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return _response(
        "VALIDATION_ERROR",
        "Request validation failed",
        exc.errors(),
        422,
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application exception", exc_info=exc)
    return _response("INTERNAL_ERROR", "Internal server error", None, 500)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
