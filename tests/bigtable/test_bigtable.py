"""Bigtable tests using the real client, served by drongo's gRPC emulator."""

from __future__ import annotations

import pytest

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")


def _table(name="users", families=("cf",)):
    from google.cloud import bigtable
    from google.cloud.bigtable import column_family

    client = bigtable.Client(project="test-project", admin=True)
    table = client.instance("inst").table(name)
    table.create(
        column_families={f: column_family.MaxVersionsGCRule(3) for f in families}
    )
    return table


# -- admin ------------------------------------------------------------------


def test_create_get_list_delete_table() -> None:
    from google.cloud import bigtable

    table = _table()
    assert table.exists()

    client = bigtable.Client(project="test-project", admin=True)
    instance = client.instance("inst")
    names = [t.table_id for t in instance.list_tables()]
    assert names == ["users"]

    table.delete()
    assert not table.exists()


def test_duplicate_table_conflicts() -> None:
    from google.api_core import exceptions as gexc
    from google.cloud.bigtable import column_family

    table = _table()
    with pytest.raises(gexc.AlreadyExists):
        table.create(column_families={"cf": column_family.MaxVersionsGCRule(1)})


# -- data: writes and reads -------------------------------------------------


def test_set_cell_and_read_row() -> None:
    table = _table()
    row = table.direct_row(b"user#1")
    row.set_cell("cf", b"name", b"Alice")
    row.set_cell("cf", b"age", b"30")
    row.commit()

    read = table.read_row(b"user#1")
    assert read.cells["cf"][b"name"][0].value == b"Alice"
    assert read.cells["cf"][b"age"][0].value == b"30"


def test_read_missing_row_is_none() -> None:
    table = _table()
    assert table.read_row(b"nope") is None


def test_multiple_versions_newest_first() -> None:
    table = _table()
    for i, value in enumerate([b"v1", b"v2", b"v3"]):
        row = table.direct_row(b"r")
        # explicit increasing timestamps (micros, ms-aligned)
        row.set_cell("cf", b"q", value, timestamp=_ts(1000 + i))
        row.commit()

    cells = table.read_row(b"r").cells["cf"][b"q"]
    assert [c.value for c in cells] == [b"v3", b"v2", b"v1"]


def test_delete_cell_family_row() -> None:
    table = _table(families=("cf", "other"))
    row = table.direct_row(b"r")
    row.set_cell("cf", b"a", b"1")
    row.set_cell("cf", b"b", b"2")
    row.set_cell("other", b"c", b"3")
    row.commit()

    d = table.direct_row(b"r")
    d.delete_cell("cf", b"a")
    d.commit()
    assert b"a" not in table.read_row(b"r").cells["cf"]

    d2 = table.direct_row(b"r")
    d2.delete_cells("cf", d2.ALL_COLUMNS)
    d2.commit()
    assert "cf" not in table.read_row(b"r").cells

    d3 = table.direct_row(b"r")
    d3.delete()
    d3.commit()
    assert table.read_row(b"r") is None


# -- scans ------------------------------------------------------------------


def _seed(table) -> None:
    for key in [b"a", b"b", b"c", b"d"]:
        row = table.direct_row(key)
        row.set_cell("cf", b"v", key)
        row.commit()


def test_scan_all_rows() -> None:
    table = _table()
    _seed(table)
    assert sorted(r.row_key for r in table.read_rows()) == [b"a", b"b", b"c", b"d"]


def test_scan_row_range() -> None:
    table = _table()
    _seed(table)
    rows = table.read_rows(start_key=b"b", end_key=b"d")  # end exclusive
    assert [r.row_key for r in rows] == [b"b", b"c"]


def test_scan_with_limit() -> None:
    table = _table()
    _seed(table)
    assert [r.row_key for r in table.read_rows(limit=2)] == [b"a", b"b"]


def test_mutate_rows_batch() -> None:
    table = _table()
    r1 = table.direct_row(b"x")
    r1.set_cell("cf", b"v", b"1")
    r2 = table.direct_row(b"y")
    r2.set_cell("cf", b"v", b"2")
    table.mutate_rows([r1, r2])

    assert sorted(r.row_key for r in table.read_rows()) == [b"x", b"y"]


def test_backend_is_inspectable() -> None:
    table = _table()
    table.direct_row(b"r").set_cell("cf", b"v", b"1")
    _commit(table, b"r")
    tables = get_backend("bigtable")["test-project"].tables
    assert "projects/test-project/instances/inst/tables/users" in tables


# -- helpers ----------------------------------------------------------------


def _ts(millis: int):
    import datetime

    return datetime.datetime.fromtimestamp(millis / 1000, tz=datetime.timezone.utc)


def _commit(table, key: bytes) -> None:
    row = table.direct_row(key)
    row.set_cell("cf", b"v", b"1")
    row.commit()
