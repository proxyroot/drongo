# Quickstart

## Install

```bash
pip install drongo
```

Bring your own google-cloud client libraries. drongo mocks whatever you already
install:

```bash
pip install google-cloud-storage google-cloud-secret-manager google-cloud-pubsub
```

## Your first test

Wrap any test with `@mock_gcp`. Inside the scope, the google-cloud clients talk
to drongo's in-memory backends instead of the network:

```python
from drongo import mock_gcp


@mock_gcp
def test_upload_download():
    from google.cloud import storage

    client = storage.Client(project="my-project")
    bucket = client.create_bucket("my-bucket")

    bucket.blob("hello.txt").upload_from_string(
        "hello drongo", content_type="text/plain"
    )

    assert bucket.blob("hello.txt").download_as_text() == "hello drongo"
    assert [b.name for b in client.list_blobs("my-bucket")] == ["hello.txt"]
```

No credentials, no network, no emulator. `storage.Client()` works with or
without arguments: drongo supplies anonymous credentials and a default project
while a mock scope is active.

## Every way to invoke it

All four styles mirror moto exactly:

```python
from drongo import mock_gcp


# 1. Bare decorator
@mock_gcp
def test_a(): ...


# 2. Called decorator
@mock_gcp()
def test_b(): ...


# 3. Context manager
def test_c():
    with mock_gcp():
        ...


# 4. Class decorator (plain class or unittest.TestCase)
@mock_gcp
class TestSuite:
    def test_d(self): ...
```

Scopes are **reentrant**: nesting `@mock_gcp` inside another active scope is
safe and shares the same backends.

## pytest fixture

Installing drongo auto-registers a `drongo` pytest fixture. Request it and the
mock is active for that test, with a handle to inspect raw backend state:

```python
def test_with_fixture(drongo):
    from google.cloud import storage

    storage.Client(project="p").create_bucket("b")

    # Inspect raw backend state, moto-style.
    assert "b" in drongo.backend("storage").buckets
```

## Inspecting backend state

Every service keeps its state in an in-memory backend you can reach directly,
the same way you would with moto. `get_backend` returns a `BackendDict` keyed by
project (drongo shards state per project, just as moto keys by account + region).
This is handy for asserting on what your code wrote without reading it back
through the client:

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_inspect():
    from google.cloud import storage

    storage.Client(project="p").create_bucket("b")

    # Index the BackendDict by project. Globally-namespaced services like
    # Storage and Pub/Sub share one backend, so any project key returns it.
    assert "b" in get_backend("storage")["p"].buckets
```

The `drongo` pytest fixture offers a shortcut, `drongo.backend("storage")`, that
resolves the project for you and returns the backend directly.

## What's supported

See [Supported services](supported-services.md) for the full matrix, or jump to a
specific service in the sidebar for runnable examples.
