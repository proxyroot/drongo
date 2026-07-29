"""GCP-flavoured HTTP errors.

Google Cloud REST/JSON APIs return errors in a well-known envelope::

    {
      "error": {
        "code": 404,
        "message": "Not Found",
        "errors": [{"domain": "global", "reason": "notFound", "message": "..."}],
        "status": "NOT_FOUND"
      }
    }

The google client libraries turn the HTTP *status code* into the matching
``google.api_core.exceptions`` subclass (``NotFound``, ``Conflict`` …), so the
most important thing gato has to get right is the status code; the body simply
carries a helpful message. :class:`GatoHttpError` models that envelope and knows
how to render itself into the ``(status, headers, body)`` triple the router
returns.
"""

from __future__ import annotations

import json
from typing import Any

# Canonical google.rpc status strings keyed by HTTP status code. Not exhaustive
# - just the codes gato actually emits.
_STATUS_BY_CODE = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "ALREADY_EXISTS",
    412: "FAILED_PRECONDITION",
    429: "RESOURCE_EXHAUSTED",
    500: "INTERNAL",
    501: "NOT_IMPLEMENTED",
}


class GatoHttpError(Exception):
    """An error that should be serialised as a GCP JSON error response."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        reason: str = "",
        status: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.reason = reason
        self.status = status or _STATUS_BY_CODE.get(status_code, "UNKNOWN")
        self.errors = errors

    def to_dict(self) -> dict[str, Any]:
        errors = self.errors
        if errors is None:
            errors = [{"domain": "global", "message": self.message}]
            if self.reason:
                errors[0]["reason"] = self.reason
        return {
            "error": {
                "code": self.status_code,
                "message": self.message,
                "errors": errors,
                "status": self.status,
            }
        }

    def to_response(self) -> tuple[int, dict[str, str], str]:
        body = json.dumps(self.to_dict())
        return self.status_code, {"Content-Type": "application/json"}, body


# --- Convenience constructors ---------------------------------------------


def bad_request(message: str, *, reason: str = "invalid") -> GatoHttpError:
    return GatoHttpError(400, message, reason=reason)


def not_found(message: str, *, reason: str = "notFound") -> GatoHttpError:
    return GatoHttpError(404, message, reason=reason)


def already_exists(message: str, *, reason: str = "conflict") -> GatoHttpError:
    return GatoHttpError(409, message, reason=reason)


def precondition_failed(
    message: str, *, reason: str = "conditionNotMet"
) -> GatoHttpError:
    return GatoHttpError(412, message, reason=reason)


def not_implemented(message: str) -> GatoHttpError:
    return GatoHttpError(501, message, reason="notImplemented")
