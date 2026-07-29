# BigQuery

- **Client:** `google-cloud-bigquery`
- **Transport:** REST/JSON (the client default). drongo intercepts it directly.
- **Backend:** per-project.

Use the normal client with no changes.

!!! warning "Query execution is out of scope"
    drongo mocks BigQuery's **resource and data management**: datasets, tables,
    streaming inserts, and reading rows back. It does **not** execute SQL
    (`client.query(...)`), which would require a real SQL engine. Test your
    pipeline's reads and writes here; test your SQL against a real warehouse or a
    dedicated SQL engine.

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
| SQL query execution (`client.query(...)`) | Out of scope (needs a SQL engine) |
| Load / extract / copy jobs, routines, views | Planned |
