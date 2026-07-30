"""In-process gRPC emulator for Cloud Datastore.

Datastore is gRPC-first; the high-level ``datastore.Client`` builds an insecure
gRPC channel when ``DATASTORE_EMULATOR_HOST`` is set, so drongo runs a real
in-process gRPC server backed by :class:`DatastoreBackend` and points the client
at it via that env var. The client works unchanged.

All the RPCs the client uses are unary: ``Commit`` (put/delete), ``Lookup``
(get), ``RunQuery``, ``BeginTransaction`` / ``Rollback`` (transactions are
completed synchronously), and ``AllocateIds``. This module owns all Datastore
proto handling, including the typed ``Value`` encoding and query interpretation.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError, already_exists, not_found
from drongo.services.datastore.models import DatastoreBackend, datastore_backends

_MISSING = object()


class DatastoreEmulator(BaseEmulator):
    """Serves the Datastore gRPC API from an in-process server."""

    ENV_VAR = "DATASTORE_EMULATOR_HOST"

    def __init__(self, backends: Any = datastore_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._prev_host: str | None = None
        self._grpc: Any = None
        self._dt: Any = None

    def _backend(self, project: str) -> DatastoreBackend:
        return self._backends[project]

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
            from google.cloud.datastore_v1 import types as dt
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._dt = grpc, dt
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, dt = self._grpc, self._dt
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
            return grpc.unary_unary_rpc_method_handler(
                guard(fn),
                request_deserializer=req_t.deserialize,
                response_serializer=resp_t.serialize,
            )

        handlers = {
            "Lookup": unary(dt.LookupRequest, dt.LookupResponse, self._lookup),
            "RunQuery": unary(dt.RunQueryRequest, dt.RunQueryResponse, self._run_query),
            "Commit": unary(dt.CommitRequest, dt.CommitResponse, self._commit),
            "BeginTransaction": unary(
                dt.BeginTransactionRequest,
                dt.BeginTransactionResponse,
                self._begin_transaction,
            ),
            "Rollback": unary(dt.RollbackRequest, dt.RollbackResponse, self._rollback),
            "AllocateIds": unary(
                dt.AllocateIdsRequest, dt.AllocateIdsResponse, self._allocate_ids
            ),
            "ReserveIds": unary(
                dt.ReserveIdsRequest, dt.ReserveIdsResponse, self._reserve_ids
            ),
        }
        return (
            grpc.method_handlers_generic_handler(
                "google.datastore.v1.Datastore", handlers
            ),
        )

    # -- proto helpers -----------------------------------------------------

    @staticmethod
    def _which(message: Any, oneof: str) -> str | None:
        return type(message).pb(message).WhichOneof(oneof)

    @staticmethod
    def _has(message: Any, field: str) -> bool:
        return type(message).pb(message).HasField(field)

    def _canonical(self, key: Any) -> str:
        pid = key.partition_id
        parts = [pid.project_id or "", pid.namespace_id or ""]
        for element in key.path:
            which = type(element).pb(element).WhichOneof("id_type")
            if which == "id":
                ident = f"i{element.id}"
            elif which == "name":
                ident = f"n{element.name}"
            else:
                ident = "?"
            parts.append(f"{element.kind}={ident}")
        return "|".join(parts)

    def _is_incomplete(self, key: Any) -> bool:
        if not key.path:
            return True
        last = key.path[-1]
        return type(last).pb(last).WhichOneof("id_type") is None

    def _clone(self, message: Any) -> Any:
        cls = type(message)
        return cls.deserialize(cls.serialize(message))

    def _entity_kind(self, entity: Any) -> str:
        path = entity.key.path
        return path[-1].kind if path else ""

    def _py(self, value: Any) -> Any:
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
        if kind == "blob_value":
            return value.blob_value
        if kind == "key_value":
            return self._canonical(value.key_value)
        if kind == "array_value":
            return [self._py(v) for v in value.array_value.values]
        return None

    def _property(self, entity: Any, name: str) -> Any:
        return entity.properties.get(name)

    # -- Lookup ------------------------------------------------------------

    def _lookup(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.project_id)
        found, missing = [], []
        for key in request.keys:
            canonical = self._canonical(key)
            entity = backend.get(canonical)
            if entity is not None:
                found.append(
                    self._dt.EntityResult(
                        entity=entity, version=backend.versions.get(canonical, 1)
                    )
                )
            else:
                missing.append(self._dt.EntityResult(entity=self._dt.Entity(key=key)))
        return self._dt.LookupResponse(found=found, missing=missing)

    # -- Commit ------------------------------------------------------------

    def _commit(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.project_id)
        results = []
        for mutation in request.mutations:
            op = self._which(mutation, "operation")
            if op == "delete":
                backend.delete(self._canonical(mutation.delete))
                results.append(self._dt.MutationResult(version=1))
                continue
            if op not in ("insert", "update", "upsert"):
                continue
            assert op is not None  # narrowed above; for the type checker

            entity = self._clone(getattr(mutation, op))
            if self._is_incomplete(entity.key):
                entity.key.path[-1].id = backend.next_id()
            canonical = self._canonical(entity.key)
            if op == "insert" and backend.exists(canonical):
                raise already_exists(f"entity already exists: {canonical}")
            if op == "update" and not backend.exists(canonical):
                raise not_found(f"no entity to update: {canonical}")
            version = backend.put(canonical, entity)
            results.append(self._dt.MutationResult(key=entity.key, version=version))
        return self._dt.CommitResponse(
            mutation_results=results, index_updates=len(results)
        )

    # -- RunQuery ----------------------------------------------------------

    def _run_query(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.project_id)
        query = request.query
        namespace = request.partition_id.namespace_id
        kinds = {k.name for k in query.kind}

        rows = []
        for entity in backend.all():
            pid = entity.key.partition_id
            if pid.namespace_id != namespace:
                continue
            if kinds and self._entity_kind(entity) not in kinds:
                continue
            if self._has(query, "filter") and not self._match_filter(
                entity, query.filter
            ):
                continue
            rows.append(entity)

        for order in reversed(list(query.order)):
            descending = order.direction == self._dt.PropertyOrder.Direction.DESCENDING

            def key(entity: Any, name: str = order.property.name) -> Any:
                return self._order_key(entity, name)

            rows.sort(key=key, reverse=descending)

        offset = query.offset or 0
        if offset:
            rows = rows[offset:]
        if self._has(query, "limit"):
            rows = rows[: int(query.limit)]

        batch = self._dt.QueryResultBatch(
            entity_results=[self._dt.EntityResult(entity=e, version=1) for e in rows],
            entity_result_type=self._dt.EntityResult.ResultType.FULL,
            more_results=self._dt.QueryResultBatch.MoreResultsType.NO_MORE_RESULTS,
            end_cursor=b"",
        )
        return self._dt.RunQueryResponse(batch=batch)

    def _match_filter(self, entity: Any, filter_: Any) -> bool:
        kind = self._which(filter_, "filter_type")
        if kind == "property_filter":
            return self._match_property(entity, filter_.property_filter)
        if kind == "composite_filter":
            composite = filter_.composite_filter
            op_and = self._dt.CompositeFilter.Operator.AND
            results = [self._match_filter(entity, f) for f in composite.filters]
            return all(results) if composite.op == op_and else any(results)
        return True

    def _match_property(self, entity: Any, property_filter: Any) -> bool:
        op_enum = self._dt.PropertyFilter.Operator
        stored = self._property(entity, property_filter.property.name)
        lhs = self._py(stored) if stored is not None else _MISSING
        rhs = self._py(property_filter.value)
        op = property_filter.op

        if op == op_enum.EQUAL:
            return lhs is not _MISSING and lhs == rhs
        if op == op_enum.NOT_EQUAL:
            return lhs is not _MISSING and lhs != rhs
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

    @staticmethod
    def _safe_cmp(a: Any, b: Any) -> int | None:
        try:
            return (a > b) - (a < b)
        except TypeError:
            return None

    def _order_key(self, entity: Any, name: str) -> tuple[int, Any]:
        stored = self._property(entity, name)
        return self._rank(self._py(stored) if stored is not None else None)

    @staticmethod
    def _rank(value: Any) -> tuple[int, Any]:
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

    # -- transactions / ids ------------------------------------------------

    def _begin_transaction(self, request: Any, context: Any) -> Any:
        seq = self._backend(request.project_id).next_transaction()
        return self._dt.BeginTransactionResponse(
            transaction=f"drongo-txn-{seq}".encode()
        )

    def _rollback(self, request: Any, context: Any) -> Any:
        return self._dt.RollbackResponse()

    def _allocate_ids(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.project_id)
        keys = []
        for key in request.keys:
            completed = self._clone(key)
            if completed.path:
                completed.path[-1].id = backend.next_id()
            keys.append(completed)
        return self._dt.AllocateIdsResponse(keys=keys)

    def _reserve_ids(self, request: Any, context: Any) -> Any:
        return self._dt.ReserveIdsResponse()
