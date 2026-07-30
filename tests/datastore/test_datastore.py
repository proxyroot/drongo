"""Datastore tests using the real client, served by drongo's gRPC emulator."""

from __future__ import annotations

import pytest

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")


def _client():
    from google.cloud import datastore

    return datastore.Client(project="test-project")


def _entity(client, kind, ident, **props):
    from google.cloud import datastore

    key = client.key(kind, ident) if ident is not None else client.key(kind)
    entity = datastore.Entity(key=key)
    entity.update(props)
    return entity


# -- put / get / delete -----------------------------------------------------


def test_put_and_get() -> None:
    client = _client()
    client.put(_entity(client, "Task", "t1", title="Buy milk", done=False, priority=3))

    got = client.get(client.key("Task", "t1"))
    assert dict(got) == {"title": "Buy milk", "done": False, "priority": 3}


def test_get_missing_returns_none() -> None:
    client = _client()
    assert client.get(client.key("Task", "nope")) is None


def test_put_with_auto_id() -> None:
    client = _client()
    entity = _entity(client, "Task", None, title="Auto")
    client.put(entity)
    assert entity.key.id  # an id was allocated
    assert client.get(entity.key)["title"] == "Auto"


def test_update_overwrites() -> None:
    client = _client()
    client.put(_entity(client, "Task", "t1", title="Old"))
    client.put(_entity(client, "Task", "t1", title="New", extra=1))
    assert dict(client.get(client.key("Task", "t1"))) == {"title": "New", "extra": 1}


def test_delete() -> None:
    client = _client()
    client.put(_entity(client, "Task", "t1", title="x"))
    client.delete(client.key("Task", "t1"))
    assert client.get(client.key("Task", "t1")) is None


def test_typed_values_round_trip() -> None:
    import datetime

    client = _client()
    when = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    client.put(
        _entity(
            client,
            "Doc",
            "d1",
            s="text",
            i=42,
            f=3.5,
            b=True,
            n=None,
            arr=[1, 2, 3],
            when=when,
        )
    )
    got = dict(client.get(client.key("Doc", "d1")))
    assert got["s"] == "text" and got["i"] == 42 and got["f"] == 3.5
    assert got["b"] is True and got["n"] is None and got["arr"] == [1, 2, 3]
    assert got["when"] == when


# -- queries ----------------------------------------------------------------


def _seed(client) -> None:
    client.put(_entity(client, "Task", "a", priority=1, done=False))
    client.put(_entity(client, "Task", "b", priority=2, done=True))
    client.put(_entity(client, "Task", "c", priority=3, done=False))


def test_query_all_of_kind() -> None:
    client = _client()
    _seed(client)
    client.put(_entity(client, "Other", "x", priority=9))
    keys = sorted(e.key.name for e in client.query(kind="Task").fetch())
    assert keys == ["a", "b", "c"]


def test_query_filter() -> None:
    from google.cloud.datastore.query import PropertyFilter

    client = _client()
    _seed(client)
    q = client.query(kind="Task")
    q.add_filter(filter=PropertyFilter("done", "=", False))
    assert sorted(e.key.name for e in q.fetch()) == ["a", "c"]


def test_query_inequality() -> None:
    from google.cloud.datastore.query import PropertyFilter

    client = _client()
    _seed(client)
    q = client.query(kind="Task")
    q.add_filter(filter=PropertyFilter("priority", ">=", 2))
    assert sorted(e.key.name for e in q.fetch()) == ["b", "c"]


def test_query_order_and_limit() -> None:
    client = _client()
    _seed(client)
    q = client.query(kind="Task")
    q.order = ["-priority"]
    assert [e.key.name for e in q.fetch(limit=2)] == ["c", "b"]


def test_backend_is_inspectable() -> None:
    client = _client()
    client.put(_entity(client, "Task", "t1", title="x"))
    assert len(get_backend("datastore")["test-project"].entities) == 1
