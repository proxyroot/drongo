"""In-process gRPC emulator for Cloud Firestore (Native mode).

Runs a real gRPC server backed by :class:`FirestoreBackend` and points the
client at it via ``FIRESTORE_EMULATOR_HOST``, so the user's normal client works
with no code change. Handlers are thin adapters over the backend, like moto's
``responses.py`` over ``SQSBackend``.

The Python client uses four RPCs for everyday work: ``Commit`` (set/update/
delete/add), ``BatchGetDocuments`` (``.get()``, server-streaming), ``RunQuery``
(collection queries, server-streaming), and ``ListDocuments``. This module owns
all Firestore proto handling, including the typed ``Value`` encoding and
``StructuredQuery`` interpretation (filters, ordering, limit/offset).

Required libraries (``grpcio`` plus ``google-cloud-firestore``) are optional; if
absent, :meth:`start` no-ops so drongo still works for other services.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError, already_exists, not_found
from drongo.services.firestore.models import (
    FirestoreBackend,
    StoredDocument,
    firestore_backends,
)

_GLOBAL = "_global_"
_MISSING = object()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FirestoreEmulator(BaseEmulator):
    """Serves the Firestore gRPC API from an in-process server."""

    ENV_VAR = "FIRESTORE_EMULATOR_HOST"

    def __init__(self, backends: Any = firestore_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._prev_host: str | None = None
        self._grpc: Any = None
        self._ft: Any = None

    def _backend(self) -> FirestoreBackend:
        return self._backends[_GLOBAL]

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._available is False:
            return
        if self._server is None and not self._boot():
            self._available = False
            return
        self._available = True
        self._prev_host = os.environ.get(self.ENV_VAR)
        os.environ[self.ENV_VAR] = f"localhost:{self._port}"

    def stop(self) -> None:
        if self._server is None:
            return
        if self._prev_host is None:
            os.environ.pop(self.ENV_VAR, None)
        else:
            os.environ[self.ENV_VAR] = self._prev_host
        self._prev_host = None

    def _boot(self) -> bool:
        try:
            import grpc
            from google.cloud.firestore_v1 import types as ft
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._ft = grpc, ft
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, ft = self._grpc, self._ft
        status = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
            412: grpc.StatusCode.FAILED_PRECONDITION,
        }

        def unary_guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(request: Any, context: Any) -> Any:
                try:
                    return fn(request, context)
                except DrongoHttpError as exc:
                    context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return wrapped

        def stream_guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(request: Any, context: Any) -> Iterator[Any]:
                try:
                    yield from fn(request, context)
                except DrongoHttpError as exc:
                    context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return wrapped

        def unary(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            return grpc.unary_unary_rpc_method_handler(
                unary_guard(fn),
                request_deserializer=req_t.deserialize,
                response_serializer=resp_t.serialize,
            )

        def stream(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            return grpc.unary_stream_rpc_method_handler(
                stream_guard(fn),
                request_deserializer=req_t.deserialize,
                response_serializer=resp_t.serialize,
            )

        handlers = {
            "Commit": unary(ft.CommitRequest, ft.CommitResponse, self._commit),
            "BatchGetDocuments": stream(
                ft.BatchGetDocumentsRequest,
                ft.BatchGetDocumentsResponse,
                self._batch_get,
            ),
            "RunQuery": stream(
                ft.RunQueryRequest, ft.RunQueryResponse, self._run_query
            ),
            "ListDocuments": stream(
                ft.ListDocumentsRequest, ft.ListDocumentsResponse, self._list_documents
            ),
        }
        return (
            self._grpc.method_handlers_generic_handler(
                "google.firestore.v1.Firestore", handlers
            ),
        )

    # -- proto helpers -----------------------------------------------------

    @staticmethod
    def _which(message: Any, oneof: str) -> str | None:
        return type(message).pb(message).WhichOneof(oneof)

    @staticmethod
    def _has(message: Any, field: str) -> bool:
        return type(message).pb(message).HasField(field)

    def _clone_fields(self, document: Any) -> dict[str, Any]:
        """Detach a document's Value fields from the (soon-freed) request."""
        value_t = self._ft.Value
        return {
            key: value_t.deserialize(value_t.serialize(value))
            for key, value in document.fields.items()
        }

    def _to_document(self, entry: StoredDocument) -> Any:
        return self._ft.Document(
            name=entry.name,
            fields=entry.fields,
            create_time=entry.create_time,
            update_time=entry.update_time,
        )

    def _py(self, value: Any) -> Any:
        """Decode a Firestore ``Value`` proto to a comparable Python value."""
        if value is None:
            return None
        kind = type(value).pb(value).WhichOneof("value_type")
        if kind in (None, "null_value"):
            return None
        if kind == "boolean_value":
            return value.boolean_value
        if kind == "integer_value":
            return value.integer_value
        if kind == "double_value":
            return value.double_value
        if kind == "string_value":
            return value.string_value
        if kind == "timestamp_value":
            return value.timestamp_value
        if kind == "bytes_value":
            return value.bytes_value
        if kind == "reference_value":
            return value.reference_value
        if kind == "array_value":
            return [self._py(item) for item in value.array_value.values]
        if kind == "map_value":
            return {k: self._py(v) for k, v in value.map_value.fields.items()}
        return None

    def _field_value(self, entry: StoredDocument, field_path: str) -> Any:
        """Return the ``Value`` proto at ``field_path`` (dotted), or ``None``."""
        current = entry.fields
        value = None
        parts = field_path.split(".")
        for index, part in enumerate(parts):
            if part not in current:
                return None
            value = current[part]
            if index < len(parts) - 1:
                if type(value).pb(value).WhichOneof("value_type") != "map_value":
                    return None
                current = dict(value.map_value.fields)
        return value

    # -- Commit ------------------------------------------------------------

    def _commit(self, request: Any, context: Any) -> Any:
        backend = self._backend()
        results = []
        for write in request.writes:
            self._check_precondition(backend, write)
            operation = self._which(write, "operation")
            if operation == "update":
                document = write.update
                fields = self._clone_fields(document)
                if self._has(write, "update_mask"):
                    backend.merge(
                        document.name, fields, list(write.update_mask.field_paths)
                    )
                else:
                    backend.put(document.name, fields)
            elif operation == "delete":
                backend.delete(write.delete)
            results.append(self._ft.WriteResult(update_time=_now()))
        return self._ft.CommitResponse(write_results=results, commit_time=_now())

    def _check_precondition(self, backend: FirestoreBackend, write: Any) -> None:
        if not self._has(write, "current_document"):
            return
        precondition = write.current_document
        if self._which(precondition, "condition_type") != "exists":
            return
        name = (
            write.update.name
            if self._which(write, "operation") == "update"
            else (write.delete)
        )
        if precondition.exists and not backend.exists(name):
            raise not_found(f"No document to update: {name}")
        if not precondition.exists and backend.exists(name):
            raise already_exists(f"Document already exists: {name}")

    # -- BatchGetDocuments (streaming) -------------------------------------

    def _batch_get(self, request: Any, context: Any) -> Iterator[Any]:
        backend = self._backend()
        for name in request.documents:
            entry = backend.get(name)
            if entry is None:
                yield self._ft.BatchGetDocumentsResponse(missing=name, read_time=_now())
            else:
                yield self._ft.BatchGetDocumentsResponse(
                    found=self._to_document(entry), read_time=entry.update_time
                )

    # -- ListDocuments (streaming per the client's paged reader) -----------

    def _list_documents(self, request: Any, context: Any) -> Iterator[Any]:
        collection_path = f"{request.parent}/{request.collection_id}"
        entries = self._backend().list_collection(collection_path)
        yield self._ft.ListDocumentsResponse(
            documents=[self._to_document(e) for e in entries]
        )

    # -- RunQuery (streaming) ----------------------------------------------

    def _run_query(self, request: Any, context: Any) -> Iterator[Any]:
        query = request.structured_query
        selectors = list(query.from_)
        if not selectors:
            return
        collection_path = f"{request.parent}/{selectors[0].collection_id}"
        entries = self._backend().list_collection(collection_path)

        if self._has(query, "where"):
            entries = [e for e in entries if self._matches(e, query.where)]

        for order in reversed(list(query.order_by)):
            descending = (
                order.direction == self._ft.StructuredQuery.Direction.DESCENDING
            )

            def key(entry: StoredDocument, path: str = order.field.field_path) -> Any:
                return self._order_key(entry, path)

            entries.sort(key=key, reverse=descending)

        offset = query.offset or 0
        if offset:
            entries = entries[offset:]
        if self._has(query, "limit"):
            entries = entries[: int(query.limit)]

        for entry in entries:
            yield self._ft.RunQueryResponse(
                document=self._to_document(entry), read_time=entry.update_time
            )

    # -- query evaluation --------------------------------------------------

    def _matches(self, entry: StoredDocument, filter_: Any) -> bool:
        kind = self._which(filter_, "filter_type")
        if kind == "field_filter":
            return self._match_field(entry, filter_.field_filter)
        if kind == "unary_filter":
            return self._match_unary(entry, filter_.unary_filter)
        if kind == "composite_filter":
            composite = filter_.composite_filter
            op_and = self._ft.StructuredQuery.CompositeFilter.Operator.AND
            results = [self._matches(entry, sub) for sub in composite.filters]
            return all(results) if composite.op == op_and else any(results)
        return True

    def _match_field(self, entry: StoredDocument, field_filter: Any) -> bool:
        op_enum = self._ft.StructuredQuery.FieldFilter.Operator
        stored = self._field_value(entry, field_filter.field.field_path)
        lhs = self._py(stored) if stored is not None else _MISSING
        rhs = self._py(field_filter.value)
        op = field_filter.op

        if op == op_enum.EQUAL:
            return lhs is not _MISSING and lhs == rhs
        if op == op_enum.NOT_EQUAL:
            return lhs is not _MISSING and lhs != rhs
        if op == op_enum.ARRAY_CONTAINS:
            return isinstance(lhs, list) and rhs in lhs
        if op == op_enum.ARRAY_CONTAINS_ANY:
            return (
                isinstance(lhs, list)
                and isinstance(rhs, list)
                and any(item in lhs for item in rhs)
            )
        if op == op_enum.IN:
            return isinstance(rhs, list) and lhs is not _MISSING and lhs in rhs
        if op == op_enum.NOT_IN:
            return isinstance(rhs, list) and lhs is not _MISSING and lhs not in rhs

        if lhs is _MISSING:
            return False
        comparison = self._safe_cmp(lhs, rhs)
        if comparison is None:
            return False
        if op == op_enum.LESS_THAN:
            return comparison < 0
        if op == op_enum.LESS_THAN_OR_EQUAL:
            return comparison <= 0
        if op == op_enum.GREATER_THAN:
            return comparison > 0
        if op == op_enum.GREATER_THAN_OR_EQUAL:
            return comparison >= 0
        return False

    def _match_unary(self, entry: StoredDocument, unary: Any) -> bool:
        op_enum = self._ft.StructuredQuery.UnaryFilter.Operator
        stored = self._field_value(entry, unary.field.field_path)
        value = self._py(stored) if stored is not None else _MISSING
        if unary.op == op_enum.IS_NULL:
            return value is None
        if unary.op == op_enum.IS_NOT_NULL:
            return value is not None and value is not _MISSING
        if unary.op == op_enum.IS_NAN:
            return isinstance(value, float) and value != value
        if unary.op == op_enum.IS_NOT_NAN:
            return isinstance(value, (int, float)) and value == value
        return True

    @staticmethod
    def _safe_cmp(a: Any, b: Any) -> int | None:
        try:
            return (a > b) - (a < b)
        except TypeError:
            return None

    def _order_key(self, entry: StoredDocument, field_path: str) -> tuple[int, Any]:
        if field_path == "__name__":
            return (4, entry.name)
        stored = self._field_value(entry, field_path)
        return self._rank(self._py(stored) if stored is not None else None)

    @staticmethod
    def _rank(value: Any) -> tuple[int, Any]:
        """A (type-rank, value) key so ordering never compares across types."""
        if value is None:
            return (0, 0)
        if isinstance(value, bool):
            return (1, int(value))
        if isinstance(value, (int, float)):
            return (2, value)
        if isinstance(value, datetime):
            return (3, value)
        if isinstance(value, str):
            return (4, value)
        if isinstance(value, bytes):
            return (5, value)
        return (9, 0)
