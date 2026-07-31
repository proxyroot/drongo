# BigQuery

- **Client:** `google-cloud-bigquery`
- **Transport:** REST/JSON (the client default). drongo intercepts it directly.
- **Backend:** per-project.

Use the normal client with no changes.

SQL execution (`client.query(...)`) is available through an optional extra; see
[Running SQL queries](#running-sql-queries) below. Everything else (datasets,
tables, streaming inserts, reading rows back) works out of the box.

## Datasets and tables

```python
from drongo import mock_gcp


@mock_gcp
def test_dataset_and_table():
    from google.cloud import bigquery

    client = bigquery.Client(project="my-project")
    client.create_dataset("my-project.analytics")

    schema = [
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("age", "INTEGER"),
    ]
    table = client.create_table(
        bigquery.Table("my-project.analytics.users", schema=schema)
    )
    assert table.table_id == "users"
    assert [f.name for f in table.schema] == ["name", "age"]
```

## Streaming inserts and reading rows back

```python
@mock_gcp
def test_insert_and_read():
    from google.cloud import bigquery

    client = bigquery.Client(project="p")
    client.create_dataset("p.ds")
    client.create_table(
        bigquery.Table(
            "p.ds.users",
            schema=[
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("age", "INTEGER"),
            ],
        )
    )

    errors = client.insert_rows_json(
        "p.ds.users",
        [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}],
    )
    assert errors == []
    assert client.get_table("p.ds.users").num_rows == 2

    rows = [dict(r) for r in client.list_rows("p.ds.users")]
    assert rows == [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]
```

## Running SQL queries

`client.query(...)` runs real SQL against the tables you have seeded. It is an
optional extra because it pulls in a SQL engine:

```bash
pip install "drongo[bigquery]"
```

That installs [DuckDB](https://duckdb.org) (the engine) and
[sqlglot](https://github.com/tobymao/sqlglot) (a transpiler). sqlglot parses your
query in the BigQuery dialect and rewrites it for DuckDB, so a lot of
BigQuery-specific syntax just works: backtick table references, `SELECT *
EXCEPT(...)`, `SAFE_DIVIDE`, `FORMAT_TIMESTAMP`, `NULLS FIRST` ordering, and so
on. Your table schemas (including `REPEATED` arrays and `RECORD` structs) are fed
through the same transpiler, so joins, aggregates, `UNNEST`, and struct access
all work.

```python
@mock_gcp
def test_query():
    from google.cloud import bigquery

    client = bigquery.Client(project="p")
    client.create_dataset("p.sales")
    client.create_table(
        bigquery.Table(
            "p.sales.orders",
            schema=[
                bigquery.SchemaField("cust", "STRING"),
                bigquery.SchemaField("total", "FLOAT"),
            ],
        )
    )
    client.insert_rows_json(
        "p.sales.orders",
        [
            {"cust": "ann", "total": 10.0},
            {"cust": "ann", "total": 5.5},
            {"cust": "bob", "total": 7.0},
        ],
    )

    rows = list(
        client.query(
            "SELECT cust, SUM(total) AS spent FROM `p.sales.orders` "
            "GROUP BY cust ORDER BY spent DESC"
        ).result()
    )
    assert [(r.cust, r.spent) for r in rows] == [("ann", 15.5), ("bob", 7.0)]
```

Values come back typed, so a test can catch a real SQL mistake, not just a Python
one. This is a large common subset of GoogleSQL, not a perfect reproduction: a
BigQuery-only function with no DuckDB equivalent may still behave differently.
Seed tables the same way you would in real code (`create_table` +
`insert_rows_json`, or your app's own setup) and the query sees exactly those.

## `exists_ok` and error mapping

Missing resources raise `google.api_core.exceptions.NotFound`; duplicates raise
`Conflict`. `exists_ok=True` fetches instead of raising, just like the real
client:

```python
from google.api_core import exceptions as gexc


@mock_gcp
def test_errors():
    from google.cloud import bigquery

    client = bigquery.Client(project="p")
    client.create_dataset("p.ds")

    # exists_ok makes create fetch instead of raising Conflict.
    assert client.create_dataset("p.ds", exists_ok=True).dataset_id == "ds"

    try:
        client.get_dataset("p.ghost")
    except gexc.NotFound:
        pass
```

## Seeding rows automatically

`drongo.seed.bigquery_rows` reads a table's schema and streams typed fake rows
into it. See the [seeding guide](../seeding.md):

```python
from drongo import seed

seed.bigquery_rows(client, "p.ds.users", count=100)  # typed by schema
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete dataset | Supported |
| Create / get / list / delete table (with schema) | Supported |
| Streaming inserts (`insert_rows_json` / `insertAll`) | Supported |
| Read rows (`list_rows` / `tabledata.list`) | Supported |
| SQL query execution (`client.query(...)`) | Supported via `drongo[bigquery]` |
| Load / extract / copy jobs, routines, views | Planned |
