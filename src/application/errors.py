"""Application-level errors. The API layer maps each one to an HTTP status.

Every error carries a stable machine-readable ``code``, the user-facing
``message`` (``str(exc)``) and an optional ``corrective_action`` plus the
relevant ``field`` / workflow ``stage``. The API adds a correlation id for logs
(customer-facing error handling, R20) and never exposes stack traces or paths.
"""


class ApplicationError(Exception):
    status_code = 500
    code = "INTERNAL"

    def __init__(self, message: str, *, code: str | None = None,
                 corrective_action: str | None = None, field: str | None = None,
                 stage: str | None = None):
        super().__init__(message)
        self.code = code or self.code
        self.corrective_action = corrective_action
        self.field = field
        self.stage = stage

    def to_dict(self, correlation_id: str | None = None) -> dict:
        out = {"code": self.code, "message": str(self)}
        if self.corrective_action:
            out["corrective_action"] = self.corrective_action
        if self.field:
            out["field"] = self.field
        if self.stage:
            out["stage"] = self.stage
        if correlation_id:
            out["correlation_id"] = correlation_id
        return out


class NotFoundError(ApplicationError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(ApplicationError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(ApplicationError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(ApplicationError):
    status_code = 409
    code = "CONFLICT"


class InvalidRequestError(ApplicationError):
    status_code = 400
    code = "INVALID_REQUEST"


class ValidationError(ApplicationError):
    """Structural validation of a payload (distinct from business-rule rejections, 400)."""
    status_code = 422
    code = "VALIDATION_FAILED"


class OperationFailedError(ApplicationError):
    status_code = 500
    code = "OPERATION_FAILED"
