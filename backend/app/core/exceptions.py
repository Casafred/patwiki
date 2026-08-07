from __future__ import annotations


class AppException(Exception):
    """Base exception for expected application errors."""

    def __init__(self, code: str, message: str, status_code: int = 400, detail: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFoundException(AppException):
    def __init__(self, resource: str, resource_id: int):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} {resource_id} not found",
            status_code=404,
        )


class ValidationException(AppException):
    def __init__(self, message: str, detail: object = None):
        super().__init__("VALIDATION_ERROR", message, 422, detail)


class ConflictException(AppException):
    def __init__(self, message: str, detail: object = None):
        super().__init__("CONFLICT", message, 409, detail)
