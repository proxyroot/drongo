# Generating fake data with Faker

`drongo.seed` fills the mocked services with realistic test data, so you don't
have to hand-write fixtures. It uses [Faker](https://faker.readthedocs.io/) and
drives the **real** google-cloud clients inside a `mock_gcp` scope, so the data
lands in the in-memory backends exactly like your code's own writes.

## Install

Faker is an optional dependency:

```bash
pip install "drongo[faker]"
```

Calling a seeder without Faker installed raises a clear `ImportError` telling you
to install the extra.

## API

All seeders take a client you already built inside the mock scope, so they use
the same project and mock backends as your code.

### `seed.bigquery_rows(client, table, count=10, *, overrides=None)`

Generate `count` rows that match a table's schema and stream-insert them
(`insert_rows_json`). Returns the generated rows.

```python
from drongo import mock_gcp, seed


@mock_gcp
def test_orders():
    from google.cloud import bigquery

    client = bigquery.Client(project="shop")
    client.create_dataset("shop.analytics")
    client.create_table(
        bigquery.Table(
            "shop.analytics.orders",
            schema=[
                bigquery.SchemaField("order_id", "STRING"),
                bigquery.SchemaField("amount", "FLOAT"),
                bigquery.SchemaField("quantity", "INTEGER"),
                bigquery.SchemaField("paid", "BOOLEAN"),
            ],
        )
    )

    rows = seed.bigquery_rows(client, "shop.analytics.orders", count=500)

    assert len(rows) == 500
    assert len(list(client.list_rows("shop.analytics.orders"))) == 500
```

Values are generated per BigQuery column type:

| BigQuery type | Generated value |
| --- | --- |
| `STRING` | a word |
| `INTEGER` / `INT64` | int in `[0, 100000]` |
| `FLOAT` / `NUMERIC` | float in `[0, 10000]`, 2 dp |
| `BOOLEAN` | bool |
| `TIMESTAMP` / `DATETIME` | ISO-8601 datetime |
| `DATE` | date |
| `BYTES` | base64 of 16 random bytes |
| anything else | a word |

Pin specific columns with `overrides`:

```python
seed.bigquery_rows(client, "shop.analytics.orders", count=10,
                   overrides={"paid": True})
```

### `seed.storage_blobs(client, bucket, count=10, *, prefix="file", suffix=".txt")`

Upload `count` fake text objects to a bucket. Returns the blob names.

```python
from google.cloud import storage

gcs = storage.Client(project="shop")
gcs.create_bucket("dropzone")
names = seed.storage_blobs(gcs, "dropzone", count=25, prefix="invoice", suffix=".txt")
```

### `seed.pubsub_messages(publisher, topic, count=10)`

Publish `count` fake messages to a topic. Returns the message ids.

```python
from google.cloud import pubsub_v1

publisher = pubsub_v1.PublisherClient()
publisher.create_topic(request={"name": "projects/shop/topics/events"})
seed.pubsub_messages(publisher, "projects/shop/topics/events", count=50)
```

## Reproducible runs

Seed Faker for deterministic data:

```python
from drongo import seed

seed.seed(1234)  # same data every run
```

## Notes

- Seeders are ordinary Python; use them to build any starting state, then run the
  code under test against it.
- `bigquery_rows` fills every column by type. If your code reads specific values,
  set them with `overrides` so assertions are stable.
