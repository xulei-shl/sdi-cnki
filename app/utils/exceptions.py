from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: int | str | None = None):
        msg = f"{resource} not found" + (f": {resource_id}" if resource_id else "")
        super().__init__(message=msg, code="NOT_FOUND", status_code=404)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message=message, code="PERMISSION_DENIED", status_code=403)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, code="AUTH_FAILED", status_code=401)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR", status_code=400)


class DuplicateError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="DUPLICATE", status_code=409)


class TaskQueueError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="TASK_QUEUE_ERROR", status_code=500)
