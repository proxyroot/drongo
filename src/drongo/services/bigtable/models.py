"""In-memory models for Cloud Bigtable.

Bigtable is gRPC-first and the client connects insecurely when
``BIGTABLE_EMULATOR_HOST`` is set, so drongo serves it from an in-process gRPC
emulator (see emulator.py) that speaks both the admin API (tables, column
families) and the data API (row mutations, reads). This layer stores tables and
their rows; the emulator owns all Bigtable proto handling, including the
``ReadRows`` cell-chunk protocol.

A row's cells are ``{family: {qualifier: [(timestamp_micros, value), ...]}}`` with
newest versions first, mirroring Bigtable's versioned cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["BigtableBackend", "Table", "bigtable_backends"]

# family -> qualifier(bytes) -> list of (timestamp_micros, value bytes), newest first
Cells = dict[str, dict[bytes, list[tuple[int, bytes]]]]


@dataclass
class Table:
    name: str
    column_families: dict[str, Any] = field(default_factory=dict)
    rows: dict[bytes, Cells] = field(default_factory=dict)


class BigtableBackend(BaseBackend):
    """In-memory Bigtable state for a single project."""

    def setup(self) -> None:
        self.tables: dict[str, Table] = {}

    # -- admin -------------------------------------------------------------

    def create_table(
        self, parent: str, table_id: str, families: dict[str, Any]
    ) -> Table:
        name = f"{parent}/tables/{table_id}"
        if name in self.tables:
            raise exceptions.already_exists(f"Table already exists: {name}")
        table = Table(name=name, column_families=dict(families))
        self.tables[name] = table
        return table

    def get_table(self, name: str) -> Table:
        try:
            return self.tables[name]
        except KeyError:
            raise exceptions.not_found(f"Table not found: {name}")

    def list_tables(self, parent: str) -> list[Table]:
        prefix = f"{parent}/tables/"
        return [self.tables[n] for n in sorted(self.tables) if n.startswith(prefix)]

    def delete_table(self, name: str) -> None:
        self.get_table(name)
        del self.tables[name]

    def modify_families(self, name: str, add: dict[str, Any], drop: list[str]) -> Table:
        table = self.get_table(name)
        table.column_families.update(add)
        for family in drop:
            table.column_families.pop(family, None)
        return table

    # -- data --------------------------------------------------------------

    def set_cell(
        self,
        table_name: str,
        row_key: bytes,
        family: str,
        qualifier: bytes,
        timestamp_micros: int,
        value: bytes,
    ) -> None:
        table = self.get_table(table_name)
        row = table.rows.setdefault(row_key, {})
        column = row.setdefault(family, {}).setdefault(qualifier, [])
        # Replace an existing cell at this exact timestamp, else prepend (newest first).
        for index, (ts, _) in enumerate(column):
            if ts == timestamp_micros:
                column[index] = (timestamp_micros, value)
                return
        column.insert(0, (timestamp_micros, value))
        column.sort(key=lambda cell: cell[0], reverse=True)

    def delete_from_column(
        self, table_name: str, row_key: bytes, family: str, qualifier: bytes
    ) -> None:
        row = self.get_table(table_name).rows.get(row_key)
        if row and family in row:
            row[family].pop(qualifier, None)

    def delete_from_family(self, table_name: str, row_key: bytes, family: str) -> None:
        row = self.get_table(table_name).rows.get(row_key)
        if row:
            row.pop(family, None)

    def delete_row(self, table_name: str, row_key: bytes) -> None:
        self.get_table(table_name).rows.pop(row_key, None)

    def rows(self, table_name: str) -> dict[bytes, Cells]:
        return self.get_table(table_name).rows


#: Project-keyed backends, inspectable via ``get_backend("bigtable")[project]``.
bigtable_backends: BackendDict[BigtableBackend] = BackendDict(
    BigtableBackend, "bigtable"
)
