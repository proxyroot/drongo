"""Standalone-server (moto_server-style) tests over a real socket."""

from __future__ import annotations

import pytest

from drongo.server import start_background


@pytest.fixture
def drongo_server(monkeypatch):
    httpd, _thread = start_background(port=0)
    port = httpd.server_address[1]
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", f"http://localhost:{port}")
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_storage_over_real_socket(drongo_server) -> None:
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    client = storage.Client(project="srv", credentials=AnonymousCredentials())
    bucket = client.create_bucket("srv-bucket")
    bucket.blob("a.txt").upload_from_string("via socket")

    assert bucket.blob("a.txt").download_as_text() == "via socket"
    assert [b.name for b in client.list_blobs("srv-bucket")] == ["a.txt"]
