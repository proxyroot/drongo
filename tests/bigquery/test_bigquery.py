"""BigQuery tests using the real client (REST), served by drongo."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"


def _client():
    from google.cloud import bigquery

    return bigquery.Client(project=PROJECT)


def _schema():
    from google.cloud import bigquery

    return [
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("age", "INTEGER"),
    ]


def _table(dataset: str, table: str):
    from google.cloud import bigquery

    return bigquery.Table(f"{PROJECT}.{dataset}.{table}", schema=_schema())


# -- datasets ---------------------------------------------------------------


def test_create_and_get_dataset() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    assert client.get_dataset(f"{PROJECT}.ds").dataset_id == "ds"


def test_duplicate_dataset_conflicts() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    with pytest.raises(gexc.Conflict):
        client.create_dataset(f"{PROJECT}.ds")


def test_create_dataset_exists_ok() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    # exists_ok makes the client fetch instead of raising on conflict.
    assert client.create_dataset(f"{PROJECT}.ds", exists_ok=True).dataset_id == "ds"


def test_get_missing_dataset_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_dataset(f"{PROJECT}.ghost")


def test_list_and_delete_datasets() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.a")
    client.create_dataset(f"{PROJECT}.b")
    assert sorted(d.dataset_id for d in client.list_datasets()) == ["a", "b"]

    client.delete_dataset(f"{PROJECT}.a")
    assert [d.dataset_id for d in client.list_datasets()] == ["b"]


# -- tables -----------------------------------------------------------------


def test_create_table_with_schema() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    table = client.create_table(_table("ds", "users"))
    assert table.table_id == "users"
    assert [f.name for f in table.schema] == ["name", "age"]


def test_create_table_missing_dataset_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().create_table(_table("nope", "users"))


def test_list_and_delete_tables() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(_table("ds", "t1"))
    client.create_table(_table("ds", "t2"))
    assert sorted(t.table_id for t in client.list_tables(f"{PROJECT}.ds")) == [
        "t1",
        "t2",
    ]

    client.delete_table(f"{PROJECT}.ds.t1")
    assert [t.table_id for t in client.list_tables(f"{PROJECT}.ds")] == ["t2"]


# -- streaming inserts + read back ------------------------------------------


def test_insert_rows_and_read_back() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(_table("ds", "users"))

    errors = client.insert_rows_json(
        f"{PROJECT}.ds.users",
        [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}],
    )
    assert errors == []
    assert client.get_table(f"{PROJECT}.ds.users").num_rows == 2

    rows = [dict(r) for r in client.list_rows(f"{PROJECT}.ds.users")]
    assert rows == [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]


def test_backend_is_inspectable() -> None:
    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    assert "ds" in get_backend("bigquery")[PROJECT].datasets


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (
            "2026-07-30T12:00:00+00:00",
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        ),
        ("2026-07-30T12:00:00Z", datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)),
        ("2026-07-30 12:00:00 UTC", datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)),
        ("2026-07-30T12:00:00", datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)),
        (
            "2026-07-30T14:30:00+02:30",
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        ),
        (1785585600, datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)),
        (1785585600.5, datetime(2026, 8, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)),
    ],
)
def test_timestamp_column_roundtrips(stored, expected) -> None:
    """Regression: TIMESTAMP cells must go out as epoch microseconds.

    Real BigQuery accepts ISO-8601 (and epoch seconds) on insert but always
    returns TIMESTAMP as epoch microseconds on ``tabledata.list``. Emitting the
    stored string verbatim made the client raise ``ValueError`` on read.
    """
    from google.cloud import bigquery

    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.ds.events",
            schema=[bigquery.SchemaField("at", "TIMESTAMP")],
        )
    )

    assert client.insert_rows_json(f"{PROJECT}.ds.events", [{"at": stored}]) == []

    rows = [dict(r) for r in client.list_rows(f"{PROJECT}.ds.events")]
    assert rows == [{"at": expected}]


def test_timestamp_microsecond_precision_is_preserved() -> None:
    from google.cloud import bigquery

    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.ds.events",
            schema=[bigquery.SchemaField("at", "TIMESTAMP")],
        )
    )
    client.insert_rows_json(
        f"{PROJECT}.ds.events", [{"at": "2026-07-30T12:00:00.123456+00:00"}]
    )

    (row,) = list(client.list_rows(f"{PROJECT}.ds.events"))
    assert row["at"] == datetime(2026, 7, 30, 12, 0, 0, 123456, tzinfo=timezone.utc)


def test_null_and_unparseable_timestamps_are_tolerated() -> None:
    from google.cloud import bigquery

    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.ds.events",
            schema=[bigquery.SchemaField("at", "TIMESTAMP")],
        )
    )
    client.insert_rows_json(f"{PROJECT}.ds.events", [{"at": None}])

    assert [dict(r) for r in client.list_rows(f"{PROJECT}.ds.events")] == [{"at": None}]
