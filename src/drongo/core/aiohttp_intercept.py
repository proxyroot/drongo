"""In-process interception for aiohttp-based Google clients.

The ``responses`` library intercepts ``requests`` (sync clients). Async clients
such as ``gcloud.aio.pubsub`` talk to Google over aiohttp instead, so they need
their own seam. This patches :meth:`aiohttp.ClientSession._request` - the single
coroutine every verb method funnels through - and serves matching requests from
the same :class:`~drongo.core.responses.BaseResponse` routers used by the sync
HTTP layer. Non-matching requests fall through to real aiohttp untouched.

Routing is by path (``handle`` matches the URL path against a service's routes),
gated by host so we only ever look at Google endpoints or the local emulator
host that ``gcloud.aio`` targets when ``*_EMULATOR_HOST`` is set. If aiohttp is
not installed, :meth:`start` no-ops.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from drongo.core.registry import ServiceDefinition
from drongo.core.responses import Request

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


class AiohttpInterceptor:
    """Patches aiohttp to serve registered REST services in-process."""

    def __init__(self, services: Callable[[], list[ServiceDefinition]]) -> None:
        self._services = services
        self._orig: Any = None

    def start(self) -> None:
        try:
            import aiohttp
        except ImportError:  # pragma: no cover - aiohttp not installed
            return
        if self._orig is not None:  # already patched
            return

        self._orig = aiohttp.ClientSession._request
        interceptor = self
        original = self._orig

        async def _request(
            session: Any, method: str, str_or_url: Any, **kwargs: Any
        ) -> Any:
            served = interceptor._serve(method, str(str_or_url), kwargs)
            if served is not None:
                return served
            return await original(session, method, str_or_url, **kwargs)

        aiohttp.ClientSession._request = _request  # type: ignore[assignment]

    def stop(self) -> None:
        if self._orig is None:
            return
        import aiohttp

        aiohttp.ClientSession._request = self._orig  # type: ignore[method-assign]
        self._orig = None

    # -- dispatch ----------------------------------------------------------

    def _serve(self, method: str, url: str, kwargs: dict[str, Any]) -> Any:
        parsed = urlparse(url)
        if not _is_mock_host(parsed.hostname, parsed.port):
            return None
        request = _build_request(method, url, parsed, kwargs)
        for service in self._services():
            if service.response is None:
                continue
            response = service.response.handle(request)
            if response is not None:
                return _FakeResponse(method, url, response)
        return None


def _is_mock_host(host: str | None, port: int | None) -> bool:
    if not host:
        return False
    if host in _LOCAL_HOSTS or host == "googleapis.com" or host.endswith(".googleapis.com"):
        return True
    # The host gcloud.aio targets when an emulator env var is set.
    hostport = f"{host}:{port}" if port else host
    return any(
        os.environ[name] == hostport
        for name in os.environ
        if name.endswith("_EMULATOR_HOST")
    )


def _build_request(
    method: str, url: str, parsed: Any, kwargs: dict[str, Any]
) -> Request:
    body = _body_bytes(kwargs)
    query = parse_qs(parsed.query, keep_blank_values=True)
    params = kwargs.get("params")
    if isinstance(params, dict):
        for key, value in params.items():
            query.setdefault(key, []).append(str(value))
    headers = {str(k): str(v) for k, v in dict(kwargs.get("headers") or {}).items()}
    return Request(
        method=method.upper(),
        url=url,
        path=parsed.path,
        headers=headers,
        query=query,
        body=body,
    )


def _body_bytes(kwargs: dict[str, Any]) -> bytes:
    data = kwargs.get("data")
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    if kwargs.get("json") is not None:
        return json.dumps(kwargs["json"]).encode("utf-8")
    return b""


class _FakeResponse:
    """A minimal aiohttp ClientResponse stand-in.

    Implements just what ``gcloud.aio``'s session wrapper touches: ``status`` /
    ``reason`` / ``headers``, ``json`` / ``text`` / ``read``, ``release`` /
    ``close``, ``raise_for_status`` and the async-context-manager protocol.
    """

    def __init__(self, method: str, url: str, response: tuple) -> None:
        status, headers, body = response
        self.status = status
        self.reason = HTTPStatus(status).phrase if status in _PHRASES else ""
        self.headers = dict(headers or {})
        self._body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self._method = method.upper()
        self._url = url

    async def json(self, **_kwargs: Any) -> Any:
        return json.loads(self._body.decode("utf-8")) if self._body else None

    async def text(self, encoding: str | None = None, errors: str = "strict") -> str:
        return self._body.decode(encoding or "utf-8", errors)

    async def read(self) -> bytes:
        return self._body

    def release(self) -> None:
        return None

    def close(self) -> None:
        return None

    @property
    def request_info(self) -> Any:
        import aiohttp
        from multidict import CIMultiDict, CIMultiDictProxy
        from yarl import URL

        url = URL(self._url)
        headers: Any = CIMultiDictProxy(CIMultiDict())
        return aiohttp.RequestInfo(url, self._method, headers, url)

    @property
    def history(self) -> tuple:
        return ()

    def raise_for_status(self) -> None:
        if self.status >= 400:
            import aiohttp

            raise aiohttp.ClientResponseError(
                self.request_info,
                (),
                status=self.status,
                message=self.reason,
                headers=self.headers,  # type: ignore[arg-type]
            )

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


_PHRASES = {int(status) for status in HTTPStatus}
