"""Machine-readable non-success; retained causes are never replaced by zeros."""
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INPUT_INVALID = "INPUT_INVALID"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    QUERY_DEGENERATE = "QUERY_DEGENERATE"
    ACCURACY_UNRESOLVED = "ACCURACY_UNRESOLVED"
    WORK_BUDGET_EXCEEDED = "WORK_BUDGET_EXCEEDED"
    NO_ROOT_IN_SEARCH_DOMAIN = "NO_ROOT_IN_SEARCH_DOMAIN"
    EQUILIBRIUM_UNRESOLVED = "EQUILIBRIUM_UNRESOLVED"
    SOURCE_STALE = "SOURCE_STALE"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    IO_ERROR = "IO_ERROR"


class StabilityError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"status": "error", "code": self.code.value,
                "message": str(self), "details": self.details}
