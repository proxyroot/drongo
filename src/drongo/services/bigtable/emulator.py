"""In-process gRPC emulator for Cloud Bigtable (admin + data).

Bigtable is gRPC-first and the client connects insecurely when
``BIGTABLE_EMULATOR_HOST`` is set, so drongo runs a real in-process gRPC server
backed by :class:`BigtableBackend` and points the client at it via that env var.
One server speaks both the table-admin API (`google.bigtable.admin.v2`) and the
data API (`google.bigtable.v2`).

Admin RPCs are unary (CreateTable, GetTable, ListTables, DeleteTable,
ModifyColumnFamilies). Data RPCs mix unary (MutateRow) and server-streaming
(MutateRows, ReadRows, SampleRowKeys). The trickiest bit is ``ReadRows``, whose
response is a stream of ``CellChunk`` values the client reassembles into rows;
this module emits them per row with ``commit_row`` on the last chunk.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError
from drongo.services.bigtable.models import BigtableBackend, bigtable_backends


def _now_micros() -> int:
    micros = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    return micros // 1000 * 1000  # Bigtable default granularity is milliseconds


class BigtableEmulator(BaseEmulator):
    """Serves the Bigtable admin + data gRPC APIs from an in-process server."""

    ENV_VAR = "BIGTABLE_EMULATOR_HOST"

    def __init__(self, backends: Any = bigtable_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._prev_host: str | None = None
        self._grpc: Any = None
        self._at: Any = None
        self._dt: Any = None
        self._empty: Any = None
        self._status: Any = None

    def _backend(self, resource_name: str) -> BigtableBackend:
        # projects/<p>/instances/<i>/tables/<t>  ->  project <p>
        return self._backends[resource_name.split("/")[1]]

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
            from google.cloud.bigtable_admin_v2 import types as at
            from google.cloud.bigtable_v2 import types as dt
            from google.protobuf import empty_pb2
            from google.rpc import status_pb2
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._at, self._dt = grpc, at, dt
        self._empty, self._status = empty_pb2, status_pb2
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, at, dt, empty = self._grpc, self._at, self._dt, self._empty
        status = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
        }

        def guard(fn: Callable[..., Any], stream: bool) -> Callable[..., Any]:
            def unary_wrapped(request: Any, context: Any) -> Any:
                try:
                    return fn(request, context)
                except DrongoHttpError as exc:
                    return context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            def stream_wrapped(request: Any, context: Any) -> Iterator[Any]:
                try:
                    yield from fn(request, context)
                except DrongoHttpError as exc:
                    context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return stream_wrapped if stream else unary_wrapped

        # Most messages are proto-plus (.serialize/.deserialize); Empty is a raw
        # protobuf (.SerializeToString/.FromString) - support both.
        def _ser(t: Any) -> Any:
            return getattr(t, "serialize", None) or t.SerializeToString

        def _de(t: Any) -> Any:
            return getattr(t, "deserialize", None) or t.FromString

        def unary(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            return grpc.unary_unary_rpc_method_handler(
                guard(fn, False),
                request_deserializer=_de(req_t),
                response_serializer=_ser(resp_t),
            )

        def stream(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            return grpc.unary_stream_rpc_method_handler(
                guard(fn, True),
                request_deserializer=_de(req_t),
                response_serializer=_ser(resp_t),
            )

        admin = {
            "CreateTable": unary(at.CreateTableRequest, at.Table, self._create_table),
            "GetTable": unary(at.GetTableRequest, at.Table, self._get_table),
            "ListTables": unary(
                at.ListTablesRequest, at.ListTablesResponse, self._list_tables
            ),
            "DeleteTable": unary(
                at.DeleteTableRequest, empty.Empty, self._delete_table
            ),
            "ModifyColumnFamilies": unary(
                at.ModifyColumnFamiliesRequest, at.Table, self._modify_families
            ),
        }
        data = {
            "MutateRow": unary(
                dt.MutateRowRequest, dt.MutateRowResponse, self._mutate_row
            ),
            "MutateRows": stream(
                dt.MutateRowsRequest, dt.MutateRowsResponse, self._mutate_rows
            ),
            "ReadRows": stream(
                dt.ReadRowsRequest, dt.ReadRowsResponse, self._read_rows
            ),
            "SampleRowKeys": stream(
                dt.SampleRowKeysRequest, dt.SampleRowKeysResponse, self._sample_row_keys
            ),
        }
        return (
            grpc.method_handlers_generic_handler(
                "google.bigtable.admin.v2.BigtableTableAdmin", admin
            ),
            grpc.method_handlers_generic_handler("google.bigtable.v2.Bigtable", data),
        )

    # -- proto helpers -----------------------------------------------------

    @staticmethod
    def _which(message: Any, oneof: str) -> str | None:
        return type(message).pb(message).WhichOneof(oneof)

    @staticmethod
    def _has(message: Any, field: str) -> bool:
        return type(message).pb(message).HasField(field)

    def _clone(self, message: Any) -> Any:
        cls = type(message)
        return cls.deserialize(cls.serialize(message))

    def _to_table(self, table: Any) -> Any:
        return self._at.Table(
            name=table.name,
            column_families=table.column_families,
            granularity=self._at.Table.TimestampGranularity.MILLIS,
        )

    # -- admin handlers ----------------------------------------------------

    def _create_table(self, request: Any, context: Any) -> Any:
        families = {
            name: self._clone(cf) for name, cf in request.table.column_families.items()
        }
        table = self._backend(request.parent).create_table(
            request.parent, request.table_id, families
        )
        return self._to_table(table)

    def _get_table(self, request: Any, context: Any) -> Any:
        return self._to_table(self._backend(request.name).get_table(request.name))

    def _list_tables(self, request: Any, context: Any) -> Any:
        tables = self._backend(request.parent).list_tables(request.parent)
        return self._at.ListTablesResponse(tables=[self._to_table(t) for t in tables])

    def _delete_table(self, request: Any, context: Any) -> Any:
        self._backend(request.name).delete_table(request.name)
        return self._empty.Empty()

    def _modify_families(self, request: Any, context: Any) -> Any:
        add: dict[str, Any] = {}
        drop: list[str] = []
        for mod in request.modifications:
            kind = self._which(mod, "mod")
            if kind in ("create", "update"):
                add[mod.id] = self._clone(getattr(mod, kind))
            elif kind == "drop":
                drop.append(mod.id)
        table = self._backend(request.name).modify_families(request.name, add, drop)
        return self._to_table(table)

    # -- data: mutations ---------------------------------------------------

    def _apply_mutations(self, table: str, row_key: bytes, mutations: Any) -> None:
        backend = self._backend(table)
        for mutation in mutations:
            kind = self._which(mutation, "mutation")
            if kind == "set_cell":
                sc = mutation.set_cell
                ts = sc.timestamp_micros
                if ts in (-1, 0):
                    ts = _now_micros()
                backend.set_cell(
                    table, row_key, sc.family_name, sc.column_qualifier, ts, sc.value
                )
            elif kind == "delete_from_column":
                dc = mutation.delete_from_column
                backend.delete_from_column(
                    table, row_key, dc.family_name, dc.column_qualifier
                )
            elif kind == "delete_from_family":
                backend.delete_from_family(
                    table, row_key, mutation.delete_from_family.family_name
                )
            elif kind == "delete_from_row":
                backend.delete_row(table, row_key)

    def _mutate_row(self, request: Any, context: Any) -> Any:
        self._apply_mutations(request.table_name, request.row_key, request.mutations)
        return self._dt.MutateRowResponse()

    def _mutate_rows(self, request: Any, context: Any) -> Iterator[Any]:
        entries = []
        for index, entry in enumerate(request.entries):
            self._apply_mutations(request.table_name, entry.row_key, entry.mutations)
            entries.append(
                self._dt.MutateRowsResponse.Entry(
                    index=index, status=self._status.Status(code=0)
                )
            )
        yield self._dt.MutateRowsResponse(entries=entries)

    # -- data: reads -------------------------------------------------------

    def _in_range(self, key: bytes, row_range: Any) -> bool:
        pb = type(row_range).pb(row_range)
        if pb.HasField("start_key_closed") and key < row_range.start_key_closed:
            return False
        if pb.HasField("start_key_open") and key <= row_range.start_key_open:
            return False
        if pb.HasField("end_key_closed") and key > row_range.end_key_closed:
            return False
        return not (pb.HasField("end_key_open") and key >= row_range.end_key_open)

    def _select_keys(self, request: Any, all_keys: list[bytes]) -> list[bytes]:
        row_set = request.rows
        if not row_set.row_keys and not row_set.row_ranges:
            selected = list(all_keys)
        else:
            chosen: set[bytes] = set()
            if row_set.row_keys:
                wanted = set(row_set.row_keys)
                chosen |= {k for k in all_keys if k in wanted}
            for row_range in row_set.row_ranges:
                chosen |= {k for k in all_keys if self._in_range(k, row_range)}
            selected = sorted(chosen)
        if request.rows_limit:
            selected = selected[: int(request.rows_limit)]
        return selected

    def _read_rows(self, request: Any, context: Any) -> Iterator[Any]:
        dt = self._dt
        rows = self._backend(request.table_name).rows(request.table_name)
        for row_key in self._select_keys(request, sorted(rows.keys())):
            cells = rows[row_key]
            chunks = []
            first_in_row = True
            for family in sorted(cells.keys()):
                first_in_family = True
                for qualifier in sorted(cells[family].keys()):
                    first_in_qualifier = True
                    for timestamp, value in cells[family][qualifier]:
                        chunk = dt.ReadRowsResponse.CellChunk(
                            timestamp_micros=timestamp, value=value
                        )
                        if first_in_row:
                            chunk.row_key = row_key
                            first_in_row = False
                        if first_in_family:
                            chunk.family_name = family
                            first_in_family = False
                        if first_in_qualifier:
                            chunk.qualifier = qualifier
                            first_in_qualifier = False
                        chunks.append(chunk)
            if chunks:
                chunks[-1].commit_row = True
                yield dt.ReadRowsResponse(chunks=chunks)

    def _sample_row_keys(self, request: Any, context: Any) -> Iterator[Any]:
        rows = self._backend(request.table_name).rows(request.table_name)
        offset = 0
        for row_key in sorted(rows.keys()):
            offset += 1000
            yield self._dt.SampleRowKeysResponse(row_key=row_key, offset_bytes=offset)
