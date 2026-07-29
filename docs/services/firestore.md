# Firestore

- **Client:** `google-cloud-firestore` (`firestore.Client`)
- **Transport:** gRPC (the client default). drongo runs an **in-process gRPC
  emulator** and points the client at it via `FIRESTORE_EMULATOR_HOST`.
- **Backend:** global namespace (document names already carry the project/database).

Use the **normal** client with its default transport. Nothing changes.

!!! note "Why an emulator?"
    Firestore is gRPC-first and the Python client uses server-streaming RPCs
    (`.get()` uses `BatchGetDocuments`, queries use `RunQuery`). drongo starts a
    lightweight in-process gRPC server backed by the same in-memory model layer
    as the other services, and redirects the client with the standard
    `FIRESTORE_EMULATOR_HOST` env var the client already honors. Typed field
    values (strings, numbers, booleans, timestamps, bytes, arrays, maps) round
    trip exactly.

## Documents: set, get, update, delete

```python
from drongo import mock_gcp


@mock_gcp
def test_documents():
    from google.cloud import firestore

    client = firestore.Client(project="my-project")
    doc = client.collection("users").document("alice")

    doc.set({"name": "Alice", "age": 30, "active": True})
    assert doc.get().to_dict() == {"name": "Alice", "age": 30, "active": True}

    doc.update({"age": 31})  # merges
    assert doc.get().to_dict()["age"] == 31

    doc.delete()
    assert not doc.get().exists
```

`collection.add()` generates a document id, and `set(..., merge=True)` merges
instead of replacing. Updating a document that does not exist raises
`google.api_core.exceptions.NotFound`, matching Firestore.

## Subcollections

```python
@mock_gcp
def test_subcollections():
    from google.cloud import firestore

    client = firestore.Client(project="p")
    posts = client.collection("users").document("bob").collection("posts")
    posts.document("p1").set({"title": "hello"})

    assert posts.document("p1").get().to_dict() == {"title": "hello"}
```

## Queries

`where` (via `FieldFilter`), `order_by`, `limit`, and `offset` are supported,
including composite `AND`/`OR` filters and the `in` / `array_contains` operators:

```python
@mock_gcp
def test_queries():
    from google.cloud import firestore

    client = firestore.Client(project="p")
    for name, v in [("a", 1), ("b", 2), ("c", 3), ("d", 4)]:
        client.collection("nums").document(name).set({"v": v})

    query = (
        client.collection("nums")
        .where(filter=firestore.FieldFilter("v", ">=", 2))
        .order_by("v", direction=firestore.Query.DESCENDING)
        .limit(2)
    )
    assert [d.to_dict()["v"] for d in query.stream()] == [4, 3]
```

## Inspecting state

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_inspect():
    from google.cloud import firestore

    firestore.Client(project="p").collection("c").document("d").set({"x": 1})
    documents = get_backend("firestore")["p"].documents
    assert any(name.endswith("/documents/c/d") for name in documents)
```

## Coverage

| Operation | Status |
| --- | --- |
| Document set / get / update / delete | Supported |
| `set(merge=True)`, `collection.add()` (auto id) | Supported |
| Typed values (str, int, float, bool, null, bytes, array, map, timestamp) | Supported |
| Subcollections | Supported |
| Queries: `where`, `order_by`, `limit`, `offset` | Supported |
| Composite `AND`/`OR`, `in` / `array_contains` | Supported |
| Preconditions (update requires the doc to exist) | Supported |
| Transactions, batched writes | Planned |
| Real-time listeners (`on_snapshot`) | Planned |
| Aggregation queries (`count`/`sum`/`avg`), collection-group queries | Planned |
