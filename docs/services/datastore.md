# Datastore

- **Client:** `google-cloud-datastore` (`datastore.Client`)
- **Transport:** gRPC. The client connects insecurely when
  `DATASTORE_EMULATOR_HOST` is set, so drongo runs an **in-process gRPC emulator**
  and points the client at it via that env var.
- **Backend:** per-project.

Use the **normal** client with its default transport. Nothing changes.

!!! note "Firestore in Datastore mode"
    This mocks the classic **Datastore** API (entities, kinds, keys, ancestor
    paths). Typed property values round-trip exactly, and mutations plus queries
    run against an in-memory entity store. Transactions are accepted and
    completed synchronously (no isolation is enforced).

## Entities: put, get, delete

```python
from drongo import mock_gcp


@mock_gcp
def test_entities():
    from google.cloud import datastore

    client = datastore.Client(project="my-project")

    task = datastore.Entity(key=client.key("Task", "t1"))
    task.update({"title": "Buy milk", "done": False, "priority": 3})
    client.put(task)

    assert client.get(client.key("Task", "t1"))["title"] == "Buy milk"

    # Incomplete keys get an allocated id on put.
    auto = datastore.Entity(key=client.key("Task"))
    auto.update({"title": "Auto"})
    client.put(auto)
    assert auto.key.id

    client.delete(client.key("Task", "t1"))
    assert client.get(client.key("Task", "t1")) is None
```

## Queries

`kind`, property filters (`=`, `<`, `<=`, `>`, `>=`, `IN`), ordering, and limits
work. Filters wrap in composite `AND`/`OR`:

```python
@mock_gcp
def test_queries():
    from google.cloud import datastore
    from google.cloud.datastore.query import PropertyFilter

    client = datastore.Client(project="p")
    for name, pri in [("a", 1), ("b", 2), ("c", 3)]:
        e = datastore.Entity(key=client.key("Task", name))
        e["priority"] = pri
        client.put(e)

    q = client.query(kind="Task")
    q.add_filter(filter=PropertyFilter("priority", ">=", 2))
    q.order = ["-priority"]
    assert [e.key.name for e in q.fetch()] == ["c", "b"]
```

## Coverage

| Operation | Status |
| --- | --- |
| put / get / delete (`Commit`, `Lookup`) | Supported |
| Named + auto-id keys (`AllocateIds`) | Supported |
| Typed values (str, int, float, bool, null, bytes, array, timestamp, key) | Supported |
| Queries: kind, filters, order, limit, offset | Supported |
| Composite `AND` / `OR`, `IN` / `NOT_IN` | Supported |
| Transactions (accepted, completed synchronously) | Supported |
| Ancestor queries, projections, cursors | Planned |
| Aggregation queries (`count`) | Planned |
