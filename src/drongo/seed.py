"""Generate fake data for the mocked services, using Faker.

Optional: install with ``pip install "drongo[faker]"``. The seeders drive the
real google-cloud clients inside a :func:`drongo.mock_gcp` scope, so the fake
data lands in the in-memory backends just as your code's writes would.

Example::

    from drongo import mock_gcp, seed

    @mock_gcp
    def test_report():
        from google.cloud import bigquery

        client = bigquery.Client(project="p")
        client.create_dataset("p.analytics")
        client.create_table(bigquery.Table("p.analytics.events", schema=[...]))

        rows = seed.bigquery_rows(client, "p.analytics.events", count=100)
        assert len(list(client.list_rows("p.analytics.events"))) == 100
"""

from __future__ import annotations

import base64
from datetime import timezone
from typing import Any

_FAKER: Any = None


def faker() -> Any:
    """Return a process-wide :class:`faker.Faker`, or raise a helpful error."""
    global _FAKER
    if _FAKER is None:
        try:
            from faker import Faker
        except ImportError as exc:  # pragma: no cover - exercised without faker
            raise ImportError(
                "drongo.seed needs Faker. Install it with: pip install 'drongo[faker]'"
            ) from exc
        _FAKER = Faker()
    return _FAKER


def seed(value: int) -> None:
    """Seed the underlying Faker for reproducible data."""
    from faker import Faker

    Faker.seed(value)
    faker().seed_instance(value)


def _fake_for_bigquery(field_type: str, fake: Any) -> Any:
    kind = field_type.upper()
    if kind in ("INTEGER", "INT64"):
        return fake.random_int(0, 100_000)
    if kind in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
        return round(fake.pyfloat(min_value=0, max_value=10_000), 2)
    if kind in ("BOOLEAN", "BOOL"):
        return fake.boolean()
    if kind in ("TIMESTAMP", "DATETIME"):
        return fake.date_time(tzinfo=timezone.utc).isoformat()
    if kind == "DATE":
        return fake.date()
    if kind == "BYTES":
        return base64.b64encode(fake.binary(16)).decode("ascii")
    return fake.word()


def bigquery_rows(
    client: Any,
    table: Any,
    count: int = 10,
    *,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate ``count`` fake rows from a table's schema and stream-insert them.

    ``table`` is anything ``client.get_table`` accepts (a ``dataset.table`` ref or
    a ``Table``). ``overrides`` sets fixed values for specific columns.
    """
    fake = faker()
    table_obj = client.get_table(table)
    rows: list[dict[str, Any]] = []
    for _ in range(count):
        row = {
            field.name: _fake_for_bigquery(field.field_type, fake)
            for field in table_obj.schema
        }
        if overrides:
            row.update(overrides)
        rows.append(row)
    if rows:
        client.insert_rows_json(table, rows)
    return rows


def storage_blobs(
    client: Any,
    bucket: str,
    count: int = 10,
    *,
    prefix: str = "file",
    suffix: str = ".txt",
) -> list[str]:
    """Upload ``count`` fake text blobs to ``bucket``. Returns the blob names."""
    fake = faker()
    bucket_obj = client.bucket(bucket)
    names: list[str] = []
    for index in range(count):
        name = f"{prefix}-{index}{suffix}"
        bucket_obj.blob(name).upload_from_string(
            fake.paragraph(), content_type="text/plain"
        )
        names.append(name)
    return names


def pubsub_messages(publisher: Any, topic: str, count: int = 10) -> list[str]:
    """Publish ``count`` fake messages to ``topic``. Returns the message ids."""
    fake = faker()
    ids: list[str] = []
    for _ in range(count):
        future = publisher.publish(topic, fake.sentence().encode("utf-8"))
        ids.append(future.result())
    return ids
