"""Application-level errors. The API layer maps each one to an HTTP status."""


class ApplicationError(Exception):
    status_code = 500


class NotFoundError(ApplicationError):
    status_code = 404


class ForbiddenError(ApplicationError):
    status_code = 403


class ConflictError(ApplicationError):
    status_code = 409


class InvalidRequestError(ApplicationError):
    status_code = 400


class OperationFailedError(ApplicationError):
    status_code = 500
