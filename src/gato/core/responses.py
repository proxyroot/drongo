"""Request handling for a mocked service - gato's ``BaseResponse``.

Like moto, each service ships a ``responses.py`` with a ``BaseResponse``
subclass (``StorageResponse``, ``SecretManagerResponse`` …) whose methods handle
individual API calls, plus a ``urls.py`` declaring ``url_bases`` and
``url_paths``. The very same routing table drives both execution modes:

* **in-process** - registered with the ``responses`` interception layer so the
  google client transports are served from memory (:meth:`register` /
  :meth:`dispatch`).
* **standalone server** - :mod:`gato.server` calls :meth:`handle` directly.

``url_paths`` maps ``"<METHOD> <path-regex>"`` to a handler function taking
``(self, request)``; the first match wins, so list specific paths first. This is
gato's adaptation of moto's ``url_paths`` (which maps a path regex to a single
dispatch); gato folds the HTTP method into the key so each verb gets its own
handler.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

from gato.core.exceptions import GatoHttpError

if TYPE_CHECKING:  # pragma: no cover
    import responses as responses_lib

# (status_code, headers, body)
HttpResponse = tuple[int, dict[str, str], str | bytes]

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


def _to_str(value: object) -> str:
    """Decode header keys/values that ``requests`` may hand us as bytes."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


@dataclass
class Request:
    """A decoded inbound HTTP request handed to a handler."""

    method: str
    url: str
    path: str
    headers: dict[str, str]
    query: dict[str, list]
    body: bytes
    path_params: dict[str, str] = field(default_factory=dict)

    def param(self, name: str, default: str | None = None) -> str | None:
        """Return the first value of query parameter ``name`` (or ``default``)."""
        values = self.query.get(name)
        return values[0] if values else default

    def header(self, name: str, default: str | None = None) -> str | None:
        """Case-insensitive lookup of request header ``name``."""
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return default

    def json(self) -> dict:
        """Parse the request body as JSON (``{}`` when empty)."""
        if not self.body:
            return {}
        return json.loads(self.body.decode("utf-8"))


# A handler is an unbound method: ``fn(self, request) -> HttpResponse``.
Handler = Callable[..., HttpResponse]


class BaseResponse:
    """Base class for a service's request handlers.

    ``url_bases`` and ``url_paths`` are supplied at construction (typically from
    the service's ``urls.py``); handler methods are defined on the subclass.
    """

    def __init__(self, url_bases: list[str], url_paths: dict[str, Handler]) -> None:
        self.url_bases = url_bases
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = []
        for key, handler in url_paths.items():
            method, _, regex = key.partition(" ")
            self._routes.append((method.upper(), re.compile(regex), handler))

    # -- request handling --------------------------------------------------

    def handle(self, request: Request) -> HttpResponse | None:
        """Run the matching handler, or return ``None`` if no route matches.

        ``None`` (rather than a 404) lets the standalone server try the next
        service before giving up.
        """
        for method, pattern, handler in self._routes:
            if method != request.method:
                continue
            match = pattern.fullmatch(request.path)
            if match is None:
                continue
            request.path_params = {
                key: unquote(value)
                for key, value in match.groupdict().items()
                if value is not None
            }
            try:
                return handler(self, request)
            except GatoHttpError as exc:
                return exc.to_response()
        return None

    # -- responses (in-process) integration --------------------------------

    def register(self, mock: responses_lib.RequestsMock) -> None:
        """Attach this service's dispatch to a ``responses`` mock."""
        for base in self.url_bases:
            url_matcher = re.compile(base + r"(/.*)?$")
            for method in _HTTP_METHODS:
                mock.add_callback(
                    method,
                    url_matcher,
                    callback=self.dispatch,
                    content_type=None,
                )

    def dispatch(self, prepared_request: object) -> HttpResponse:
        """``responses`` callback: decode a PreparedRequest and serve it."""
        request = self.decode(prepared_request)
        response = self.handle(request)
        if response is not None:
            return response
        return GatoHttpError(
            404,
            f"gato has no route for {request.method} {request.path}",
            reason="notFound",
        ).to_response()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def decode(prepared_request: object) -> Request:
        """Turn a ``requests`` PreparedRequest-like object into a :class:`Request`."""
        url = getattr(prepared_request, "url", "") or ""
        parsed = urlparse(url)
        raw_body = getattr(prepared_request, "body", None)
        if isinstance(raw_body, str):
            body = raw_body.encode("utf-8")
        elif isinstance(raw_body, (bytes, bytearray)):
            body = bytes(raw_body)
        else:
            body = b""
        headers = {
            _to_str(key): _to_str(value)
            for key, value in dict(
                getattr(prepared_request, "headers", {}) or {}
            ).items()
        }
        return Request(
            method=str(getattr(prepared_request, "method", "GET")).upper(),
            url=url,
            path=parsed.path,
            headers=headers,
            query=parse_qs(parsed.query, keep_blank_values=True),
            body=body,
        )


def json_response(
    obj: object, status: int = 200, headers: dict[str, str] | None = None
) -> HttpResponse:
    """Build a JSON :data:`HttpResponse`."""
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    return status, all_headers, json.dumps(obj)
