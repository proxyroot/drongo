"""Tests for drongo.seed (Faker-backed data generators)."""

from __future__ import annotations

import pytest

from drongo import seed

pytestmark = pytest.mark.usefixtures("drongo")


def _bq_table(dataset: str = "ds", table: str = "events"):
    from google.cloud import bigquery

    client = bigquery.Client(project="p")
    client.create_dataset(f"p.{dataset}")
    client.create_table(
        bigquery.Table(
            f"p.{dataset}.{table}",
            schema=[
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("count", "INTEGER"),
                bigquery.SchemaField("ratio", "FLOAT"),
                bigquery.SchemaField("active", "BOOLEAN"),
            ],
        )
    )
    return client


def test_bigquery_rows_generate_and_insert() -> None:
    client = _bq_table()
    rows = seed.bigquery_rows(client, "p.ds.events", count=25)
    assert len(rows) == 25

    listed = [dict(r) for r in client.list_rows("p.ds.events")]
    assert len(listed) == 25
    # Values are typed by the schema.
    assert isinstance(listed[0]["count"], int)
    assert isinstance(listed[0]["ratio"], float)
    assert isinstance(listed[0]["active"], bool)


def test_bigquery_rows_overrides() -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project="p")
    client.create_dataset("p.ds")
    client.create_table(
        bigquery.Table("p.ds.t", schema=[bigquery.SchemaField("kind", "STRING")])
    )
    rows = seed.bigquery_rows(client, "p.ds.t", count=5, overrides={"kind": "fixed"})
    assert [r["kind"] for r in rows] == ["fixed"] * 5


def test_storage_blobs() -> None:
    from google.cloud import storage

    client = storage.Client(project="p")
    client.create_bucket("data")
    names = seed.storage_blobs(client, "data", count=8, prefix="doc")

    assert len(names) == 8
    assert sorted(b.name for b in client.list_blobs("data")) == sorted(names)
    assert client.bucket("data").blob(names[0]).download_as_text()  # non-empty


def test_pubsub_messages() -> None:
    from google.cloud import pubsub_v1

    pub, sub = pubsub_v1.PublisherClient(), pubsub_v1.SubscriberClient()
    pub.create_topic(request={"name": "projects/p/topics/t"})
    sub.create_subscription(
        request={"name": "projects/p/subscriptions/s", "topic": "projects/p/topics/t"}
    )

    ids = seed.pubsub_messages(pub, "projects/p/topics/t", count=6)
    assert len(ids) == 6

    resp = sub.pull(
        request={"subscription": "projects/p/subscriptions/s", "max_messages": 100}
    )
    assert len(resp.received_messages) == 6


def test_seed_is_reproducible() -> None:
    seed.seed(42)
    first = seed.faker().word()
    seed.seed(42)
    second = seed.faker().word()
    assert first == second
