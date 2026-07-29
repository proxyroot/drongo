"""BigQuery tests using the real client (REST), served by drongo."""

from __future__ import annotations

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
