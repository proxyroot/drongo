"""Firestore tests using the real client, served by drongo's gRPC emulator."""

from __future__ import annotations

import pytest

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")


def _client():
    from google.cloud import firestore

    return firestore.Client(project="test-project")


# -- documents: set / get / update / delete ---------------------------------


def test_set_and_get_document() -> None:
    client = _client()
    client.collection("users").document("alice").set(
        {"name": "Alice", "age": 30, "active": True}
    )
    snap = client.collection("users").document("alice").get()
    assert snap.exists
    assert snap.to_dict() == {"name": "Alice", "age": 30, "active": True}


def test_get_missing_document() -> None:
    snap = _client().collection("users").document("ghost").get()
    assert not snap.exists
    assert snap.to_dict() is None


def test_update_merges_fields() -> None:
    client = _client()
    doc = client.collection("users").document("alice")
    doc.set({"name": "Alice", "age": 30})
    doc.update({"age": 31})
    assert doc.get().to_dict() == {"name": "Alice", "age": 31}


def test_set_merge_true() -> None:
    client = _client()
    doc = client.collection("users").document("alice")
    doc.set({"name": "Alice", "age": 30})
    doc.set({"age": 40}, merge=True)
    assert doc.get().to_dict() == {"name": "Alice", "age": 40}


def test_update_missing_raises_not_found() -> None:
    from google.api_core import exceptions as gexc

    with pytest.raises(gexc.NotFound):
        _client().collection("users").document("nope").update({"x": 1})


def test_delete_document() -> None:
    client = _client()
    doc = client.collection("users").document("alice")
    doc.set({"name": "Alice"})
    doc.delete()
    assert not doc.get().exists


def test_add_generates_id() -> None:
    client = _client()
    _, ref = client.collection("users").add({"name": "Bob"})
    assert ref.id
    assert ref.get().to_dict() == {"name": "Bob"}


# -- typed values -----------------------------------------------------------


def test_round_trips_typed_values() -> None:
    client = _client()
    data = {
        "s": "text",
        "i": 42,
        "f": 3.5,
        "b": True,
        "n": None,
        "arr": [1, 2, 3],
        "map": {"nested": "yes"},
        "bytes": b"\x00\x01",
    }
    client.collection("t").document("d").set(data)
    assert client.collection("t").document("d").get().to_dict() == data


# -- queries ----------------------------------------------------------------


def _seed_nums(client) -> None:
    for name, value in [("a", 1), ("b", 2), ("c", 3), ("d", 4)]:
        client.collection("nums").document(name).set(
            {"v": value, "even": value % 2 == 0}
        )


def test_stream_all() -> None:
    client = _client()
    _seed_nums(client)
    assert sorted(d.to_dict()["v"] for d in client.collection("nums").stream()) == [
        1,
        2,
        3,
        4,
    ]


def test_where_and_order_desc_and_limit() -> None:
    from google.cloud import firestore

    client = _client()
    _seed_nums(client)
    q = (
        client.collection("nums")
        .where(filter=firestore.FieldFilter("v", ">=", 2))
        .order_by("v", direction=firestore.Query.DESCENDING)
        .limit(2)
    )
    assert [d.to_dict()["v"] for d in q.stream()] == [4, 3]


def test_where_equality_on_bool() -> None:
    from google.cloud import firestore

    client = _client()
    _seed_nums(client)
    evens = sorted(
        d.to_dict()["v"]
        for d in client.collection("nums")
        .where(filter=firestore.FieldFilter("even", "==", True))
        .stream()
    )
    assert evens == [2, 4]


def test_where_in_operator() -> None:
    from google.cloud import firestore

    client = _client()
    _seed_nums(client)
    got = sorted(
        d.to_dict()["v"]
        for d in client.collection("nums")
        .where(filter=firestore.FieldFilter("v", "in", [1, 3]))
        .stream()
    )
    assert got == [1, 3]


# -- subcollections / listing / inspection ----------------------------------


def test_subcollection() -> None:
    client = _client()
    posts = client.collection("users").document("bob").collection("posts")
    posts.document("p1").set({"title": "hello"})
    assert posts.document("p1").get().to_dict() == {"title": "hello"}
    # A subcollection document does not leak into the parent collection.
    assert [d.id for d in client.collection("users").stream()] == []


def test_list_documents() -> None:
    client = _client()
    _seed_nums(client)
    assert sorted(d.id for d in client.collection("nums").list_documents()) == [
        "a",
        "b",
        "c",
        "d",
    ]


def test_backend_is_inspectable() -> None:
    client = _client()
    client.collection("c").document("d").set({"x": 1})
    documents = get_backend("firestore")["_"].documents
    assert any(name.endswith("/documents/c/d") for name in documents)
