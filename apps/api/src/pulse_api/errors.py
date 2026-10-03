"""Application errors mapped to HTTP responses."""


class DomainError(Exception):
    status_code = 400
    detail = "request failed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class UnauthorizedError(DomainError):
    status_code = 401
    detail = "authentication required"


class ForbiddenError(DomainError):
    status_code = 403
    detail = "forbidden"


class NotFoundError(DomainError):
    status_code = 404
    detail = "not found"


class ConflictError(DomainError):
    status_code = 409
    detail = "conflict"


class UnavailableError(DomainError):
    status_code = 503
    detail = "service unavailable"
