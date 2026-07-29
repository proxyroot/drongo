"""Cloud Storage object-level tests."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytestmark = pytest.mark.usefixtures("gato")


def _bucket(name: str = "data"):
    from google.cloud import storage

    return storage.Client(project="test-project").create_bucket(name)


def test_upload_and_download_text() -> None:
    bucket = _bucket()
    bucket.blob("greeting.txt").upload_from_string("hello", content_type="text/plain")

    blob = bucket.blob("greeting.txt")
    assert blob.download_as_text() == "hello"


def test_upload_and_download_bytes() -> None:
    bucket = _bucket()
    payload = bytes(range(256))
    bucket.blob("bin").upload_from_string(payload)
    assert bucket.blob("bin").download_as_bytes() == payload


def test_large_resumable_upload_roundtrips() -> None:
    bucket = _bucket()
    payload = b"z" * (9 * 1024 * 1024)  # exceeds the multipart threshold
    bucket.blob("big.bin").upload_from_string(payload)
    assert bucket.get_blob("big.bin").size == len(payload)
    assert bucket.blob("big.bin").download_as_bytes() == payload


def test_blob_metadata_roundtrip() -> None:
    bucket = _bucket()
    blob = bucket.blob("m.txt")
    blob.upload_from_string("x", content_type="text/plain")

    fetched = bucket.get_blob("m.txt")
    assert fetched.content_type == "text/plain"
    assert fetched.size == 1
    assert fetched.md5_hash  # populated

    fetched.metadata = {"owner": "alice"}
    fetched.patch()
    assert bucket.get_blob("m.txt").metadata == {"owner": "alice"}


def test_download_missing_blob_raises() -> None:
    bucket = _bucket()
    with pytest.raises(gexc.NotFound):
        bucket.blob("absent").download_as_text()


def test_delete_blob() -> None:
    bucket = _bucket()
    bucket.blob("d.txt").upload_from_string("bye")
    bucket.blob("d.txt").delete()
    assert bucket.blob("d.txt").exists() is False


def test_list_blobs_with_prefix_and_delimiter() -> None:
    bucket = _bucket()
    for name in ["a.txt", "logs/1.txt", "logs/2.txt", "logs/deep/3.txt"]:
        bucket.blob(name).upload_from_string("x")

    iterator = bucket.list_blobs(prefix="logs/", delimiter="/")
    files = sorted(b.name for b in iterator)
    assert files == ["logs/1.txt", "logs/2.txt"]
    assert set(iterator.prefixes) == {"logs/deep/"}


def test_copy_blob() -> None:
    bucket = _bucket()
    bucket.blob("src.txt").upload_from_string("payload", content_type="text/plain")

    copied = bucket.copy_blob(bucket.blob("src.txt"), bucket, "dst.txt")
    assert copied.name == "dst.txt"
    assert bucket.blob("dst.txt").download_as_text() == "payload"


def test_generations_increase() -> None:
    bucket = _bucket()
    bucket.blob("g.txt").upload_from_string("v1")
    first = bucket.get_blob("g.txt").generation
    bucket.blob("g.txt").upload_from_string("v2")
    second = bucket.get_blob("g.txt").generation
    assert second > first
    assert bucket.blob("g.txt").download_as_text() == "v2"
