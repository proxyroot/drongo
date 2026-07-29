"""In-process gRPC emulator for Cloud Logging (``LoggingServiceV2``).

Cloud Logging's client is gRPC-only (no REST transport, no emulator env var), so
drongo runs a real in-process gRPC server backed by :class:`LoggingBackend` and
the service's patchers inject a transport pointing at it (see
``force_local_grpc_patchers``). The high-level ``logging.Client`` defaults to
this gRPC path, so it works unchanged.

Covers the everyday entry API: ``WriteLogEntries`` (used by ``logger.log_*``),
``ListLogEntries`` (``client.list_entries``), ``DeleteLog``, and ``ListLogs``.
This module owns all LogEntry proto handling. Required libraries are optional; if
absent, :meth:`start` no-ops and :attr:`address` is ``None``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError
from drongo.services.logging.models import LoggingBackend, logging_backends

_GLOBAL = "_global_"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LoggingEmulator(BaseEmulator):
    """Serves the Cloud Logging gRPC API from an in-process server."""

    def __init__(self, backends: Any = logging_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._grpc: Any = None
        self._lg: Any = None
        self._empty: Any = None
        self._insert = 0

    @property
    def address(self) -> str | None:
        if self._server is None or self._port is None:
            return None
        return f"localhost:{self._port}"

    def _backend(self) -> LoggingBackend:
        return self._backends[_GLOBAL]

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._available is False:
            return
        if self._server is None and not self._boot():
            self._available = False
            return
        self._available = True

    def stop(self) -> None:
        return  # no env var to restore; server is reused across scopes

    def _boot(self) -> bool:
        try:
            import grpc
            from google.cloud.logging_v2 import types as lg
            from google.protobuf import empty_pb2
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._lg, self._empty = grpc, lg, empty_pb2
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, lg, empty = self._grpc, self._lg, self._empty
        status = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
        }

        def guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(request: Any, context: Any) -> Any:
                try:
                    return fn(request, context)
                except DrongoHttpError as exc:
                    return context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return wrapped

        def unary(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            ser = getattr(resp_t, "serialize", None) or resp_t.SerializeToString
            de = getattr(req_t, "deserialize", None) or req_t.FromString
            return grpc.unary_unary_rpc_method_handler(
                guard(fn), request_deserializer=de, response_serializer=ser
            )

        handlers = {
            "WriteLogEntries": unary(
                lg.WriteLogEntriesRequest, lg.WriteLogEntriesResponse, self._write
            ),
            "ListLogEntries": unary(
                lg.ListLogEntriesRequest, lg.ListLogEntriesResponse, self._list
            ),
            "DeleteLog": unary(lg.DeleteLogRequest, empty.Empty, self._delete),
            "ListLogs": unary(lg.ListLogsRequest, lg.ListLogsResponse, self._list_logs),
        }
        return (
            grpc.method_handlers_generic_handler(
                "google.logging.v2.LoggingServiceV2", handlers
            ),
        )

    @staticmethod
    def _has(message: Any, field: str) -> bool:
        return type(message).pb(message).HasField(field)

    # -- handlers ----------------------------------------------------------

    def _write(self, request: Any, context: Any) -> Any:
        backend = self._backend()
        for entry in request.entries:
            clone = self._lg.LogEntry.deserialize(self._lg.LogEntry.serialize(entry))
            if not clone.log_name:
                clone.log_name = request.log_name
            if not self._has(clone, "resource") and self._has(request, "resource"):
                clone.resource = request.resource
            for key, value in request.labels.items():
                clone.labels.setdefault(key, value)
            if not self._has(clone, "timestamp"):
                clone.timestamp = _now()
            if not clone.insert_id:
                self._insert += 1
                clone.insert_id = f"drongo-{self._insert}"
            backend.write(clone.log_name, clone)
        return self._lg.WriteLogEntriesResponse()

    def _list(self, request: Any, context: Any) -> Any:
        descending = "desc" in (request.order_by or "").lower()
        items = self._backend().list_entries(list(request.resource_names), descending)
        return self._lg.ListLogEntriesResponse(entries=[e.entry for e in items])

    def _delete(self, request: Any, context: Any) -> Any:
        self._backend().delete_log(request.log_name)
        return self._empty.Empty()

    def _list_logs(self, request: Any, context: Any) -> Any:
        parts = request.parent.split("/")
        project = parts[1] if len(parts) > 1 else ""
        return self._lg.ListLogsResponse(log_names=self._backend().list_logs(project))
