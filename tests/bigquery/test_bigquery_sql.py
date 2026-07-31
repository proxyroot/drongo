"""BigQuery SQL execution (client.query) via the DuckDB-backed engine.

These exercise the optional ``drongo[bigquery]`` extra, so they are skipped when
DuckDB/sqlglot are not installed.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from google.api_core import exceptions as gexc

pytest.importorskip("duckdb")
pytest.importorskip("sqlglot")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"


def _client():
    from google.cloud import bigquery

    return bigquery.Client(project=PROJECT)


def _seed_orders(client) -> None:
    from google.cloud import bigquery

    client.create_dataset(f"{PROJECT}.sales")
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.sales.orders",
            schema=[
                bigquery.SchemaField("id", "INTEGER"),
                bigquery.SchemaField("cust", "STRING"),
                bigquery.SchemaField("total", "FLOAT"),
                bigquery.SchemaField("ts", "TIMESTAMP"),
            ],
        )
    )
    client.insert_rows_json(
        f"{PROJECT}.sales.orders",
        [
            {"id": 1, "cust": "x", "total": 10.0, "ts": "2020-01-01T00:00:00Z"},
            {"id": 2, "cust": "x", "total": 5.5, "ts": "2020-01-02T00:00:00Z"},
            {"id": 3, "cust": "y", "total": 7.0, "ts": "2020-01-03T00:00:00Z"},
        ],
    )


def test_select_with_backtick_reference_and_order() -> None:
    client = _client()
    _seed_orders(client)
    rows = [
        dict(r)
        for r in client.query(
            "SELECT id, cust, total FROM `test-project.sales.orders` ORDER BY id"
        ).result()
    ]
    assert rows == [
        {"id": 1, "cust": "x", "total": 10.0},
        {"id": 2, "cust": "x", "total": 5.5},
        {"id": 3, "cust": "y", "total": 7.0},
    ]


def test_aggregate_returns_typed_values() -> None:
    client = _client()
    _seed_orders(client)
    rows = list(
        client.query(
            "SELECT cust, COUNT(*) AS n, SUM(total) AS s "
            "FROM sales.orders GROUP BY cust ORDER BY cust"
        ).result()
    )
    assert [(r.cust, r.n, r.s) for r in rows] == [("x", 2, 15.5), ("y", 1, 7.0)]
    # COUNT is an integer, SUM(FLOAT) is a float - the types survive the round-trip.
    assert isinstance(rows[0].n, int) and isinstance(rows[0].s, float)


def test_where_filter() -> None:
    client = _client()
    _seed_orders(client)
    rows = [
        r.id
        for r in client.query(
            "SELECT id FROM sales.orders WHERE total > 6 ORDER BY id"
        ).result()
    ]
    assert rows == [1, 3]


def test_timestamp_column_round_trips() -> None:
    client = _client()
    _seed_orders(client)
    (row,) = list(client.query("SELECT MAX(ts) AS latest FROM sales.orders").result())
    assert row.latest == datetime(2020, 1, 3, tzinfo=timezone.utc)


def test_join_across_tables() -> None:
    from google.cloud import bigquery

    client = _client()
    _seed_orders(client)
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.sales.names",
            schema=[
                bigquery.SchemaField("cust", "STRING"),
                bigquery.SchemaField("label", "STRING"),
            ],
        )
    )
    client.insert_rows_json(
        f"{PROJECT}.sales.names",
        [{"cust": "x", "label": "Ann"}, {"cust": "y", "label": "Bob"}],
    )
    rows = [
        dict(r)
        for r in client.query(
            "SELECT o.id, n.label FROM sales.orders o "
            "JOIN sales.names n ON o.cust = n.cust ORDER BY o.id"
        ).result()
    ]
    assert rows == [
        {"id": 1, "label": "Ann"},
        {"id": 2, "label": "Ann"},
        {"id": 3, "label": "Bob"},
    ]


def test_bigquery_specific_syntax_is_transpiled() -> None:
    """`SELECT * EXCEPT(...)` and SAFE_DIVIDE are BigQuery-only; sqlglot maps
    them to DuckDB equivalents."""
    client = _client()
    _seed_orders(client)
    rows = [
        dict(r)
        for r in client.query(
            "SELECT * EXCEPT(ts, cust) FROM sales.orders WHERE id = 1"
        ).result()
    ]
    assert rows == [{"id": 1, "total": 10.0}]

    (row,) = list(
        client.query(
            "SELECT SAFE_DIVIDE(10, 0) AS d FROM sales.orders LIMIT 1"
        ).result()
    )
    assert row.d is None


def test_repeated_and_record_columns() -> None:
    from google.cloud import bigquery

    client = _client()
    client.create_dataset(f"{PROJECT}.ds")
    client.create_table(
        bigquery.Table(
            f"{PROJECT}.ds.orders",
            schema=[
                bigquery.SchemaField("id", "INTEGER"),
                bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                bigquery.SchemaField(
                    "addr",
                    "RECORD",
                    fields=[
                        bigquery.SchemaField("city", "STRING"),
                        bigquery.SchemaField("zip", "INTEGER"),
                    ],
                ),
            ],
        )
    )
    client.insert_rows_json(
        f"{PROJECT}.ds.orders",
        [
            {"id": 1, "tags": ["a", "b"], "addr": {"city": "NYC", "zip": 10001}},
            {"id": 2, "tags": [], "addr": {"city": "LA", "zip": 90001}},
        ],
    )

    # Struct field access.
    rows = [
        dict(r)
        for r in client.query(
            "SELECT id, addr.city AS city FROM ds.orders ORDER BY id"
        ).result()
    ]
    assert rows == [{"id": 1, "city": "NYC"}, {"id": 2, "city": "LA"}]

    # Array UNNEST.
    unnested = [
        dict(r)
        for r in client.query(
            "SELECT id, tag FROM ds.orders, UNNEST(tags) AS tag ORDER BY id, tag"
        ).result()
    ]
    assert unnested == [{"id": 1, "tag": "a"}, {"id": 1, "tag": "b"}]


def test_query_and_wait_fast_path() -> None:
    """query_and_wait uses jobs.query (POST /queries) rather than jobs.insert."""
    client = _client()
    rows = [dict(r) for r in client.query_and_wait("SELECT 1 AS x, 'hi' AS label")]
    assert rows == [{"x": 1, "label": "hi"}]


def test_invalid_sql_raises_bad_request() -> None:
    client = _client()
    _seed_orders(client)
    with pytest.raises(gexc.BadRequest):
        client.query("SELECT * FROM sales.does_not_exist").result()
