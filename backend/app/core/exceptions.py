from __future__ import annotations

from fastapi import HTTPException


class AppException(HTTPException):
    """Base exception for expected application errors."""

    def __init__(self, code: str, message: str, status_code: int = 400, detail: object = None):
        super().__init__(status_code=status_code, detail=message if detail is None else detail)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFoundException(AppException):
    def __init__(self, resource: str, resource_id: object = None):
        message = resource if resource_id is None else f"{resource} {resource_id} not found"
        super().__init__(code="NOT_FOUND", message=message, status_code=404, detail=message)


class BadRequestException(AppException):
    def __init__(self, message: str, detail: object = None):
        super().__init__("BAD_REQUEST", message, 400, detail if detail is not None else message)


class ValidationException(AppException):
    def __init__(self, message: str, detail: object = None):
        super().__init__("VALIDATION_ERROR", message, 422, detail)


class ConflictException(AppException):
    def __init__(self, message: str, detail: object = None):
        super().__init__("CONFLICT", message, 409, detail)
