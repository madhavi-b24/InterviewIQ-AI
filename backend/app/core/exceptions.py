"""Domain exceptions + the FastAPI handlers that turn them into the error
envelope defined in API.md §0:

    { "error": { "code": "...", "message": "...", "details": {} } }

Services/repositories raise these by name; routers never build error
responses by hand.
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base for all domain errors. `code` is the machine-readable identifier
    clients can branch on; `message` is human-readable.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"


def _error_envelope(code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


# FastAPI/pydantic validation errors echo the rejected value back under
# "input" (e.g. {"loc": ["body", "password"], "input": "abc123"}) — useful
# for most fields, but for these it means the raw secret would round-trip
# into the HTTP response body (and from there into proxy/APM/error-tracker
# logs neither this app nor the client controls). Redacted unconditionally,
# regardless of which field on which request actually failed.
_SENSITIVE_FIELD_NAMES = {
    "password",
    "new_password",
    "token",
    "refresh_token",
    "access_token",
    "reset_token",
}


def _redact_sensitive_validation_input(errors: list[dict]) -> list[dict]:
    redacted = []
    for error in errors:
        loc = error.get("loc") or ()
        if "input" in error and any(part in _SENSITIVE_FIELD_NAMES for part in loc):
            error = {**error, "input": "[REDACTED]"}
        redacted.append(error)
    return redacted


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() can contain raw exception objects (pydantic puts the
        # original ValueError under ctx["error"] for validators that raise
        # one, e.g. our password-strength check) — jsonable_encoder is what
        # FastAPI's own default handler uses to make that JSON-safe; a bare
        # json.dumps() on exc.errors() directly fails on those.
        errors = _redact_sensitive_validation_input(jsonable_encoder(exc.errors()))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_envelope(
                "VALIDATION_ERROR", "Request validation failed", {"errors": errors}
            ),
        )
