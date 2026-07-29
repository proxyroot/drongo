"""Cloud Storage bucket-level tests."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytestmark = pytest.mark.usefixtures("gato")


def _client(project: str = "test-project"):
    from google.cloud import storage

    return storage.Client(project=project)


def test_create_and_get_bucket() -> None:
    client = _client()
    created = client.create_bucket("my-bucket")
    assert created.name == "my-bucket"

    fetched = client.get_bucket("my-bucket")
    assert fetched.name == "my-bucket"


def test_create_bucket_with_location() -> None:
    client = _client()
    bucket = client.bucket("euro-bucket")
    bucket.location = "EU"
    client.create_bucket(bucket)
    assert client.get_bucket("euro-bucket").location == "EU"


def test_duplicate_bucket_conflicts() -> None:
    client = _client()
    client.create_bucket("dup")
    with pytest.raises(gexc.Conflict):
        client.create_bucket("dup")


def test_get_missing_bucket_raises_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_bucket("ghost")


def test_bucket_exists() -> None:
    client = _client()
    assert client.bucket("nope").exists() is False
    client.create_bucket("real")
    assert client.bucket("real").exists() is True


def test_list_buckets_filtered_by_project() -> None:
    _client("project-a").create_bucket("a1")
    _client("project-a").create_bucket("a2")
    _client("project-b").create_bucket("b1")

    names_a = {b.name for b in _client("project-a").list_buckets()}
    assert names_a == {"a1", "a2"}


def test_delete_bucket() -> None:
    client = _client()
    client.create_bucket("temp")
    client.bucket("temp").delete()
    assert client.bucket("temp").exists() is False


def test_delete_non_empty_bucket_conflicts() -> None:
    client = _client()
    bucket = client.create_bucket("full")
    bucket.blob("x").upload_from_string("data")
    with pytest.raises(gexc.Conflict):
        bucket.delete()


def test_delete_non_empty_bucket_with_force() -> None:
    client = _client()
    bucket = client.create_bucket("force")
    bucket.blob("x").upload_from_string("data")
    bucket.delete(force=True)
    assert client.bucket("force").exists() is False
