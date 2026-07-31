# Cloud Storage

- **Client:** `google-cloud-storage`
- **Transport:** JSON API (the client default). drongo intercepts it directly.
- **Backend:** global namespace (buckets are shared across projects, exactly as
  moto special-cases S3).

Use the normal client with no changes.

## Buckets and objects

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

## Uploads: simple, multipart, resumable

The client picks an upload strategy based on payload size and arguments. drongo
handles all three transparently:

```python
@mock_gcp
def test_uploads():
    from google.cloud import storage

    client = storage.Client(project="p")
    bucket = client.create_bucket("b")

    # Simple/media upload
    bucket.blob("small.txt").upload_from_string("small")

    # Multipart upload (metadata + media in one request)
    blob = bucket.blob("meta.txt")
    blob.metadata = {"team": "payments"}
    blob.upload_from_string("with metadata", content_type="text/plain")

    # Resumable upload (large payloads, chunked)
    big = bucket.blob("big.bin")
    big.chunk_size = 256 * 1024
    big.upload_from_string(b"x" * (1024 * 1024))

    assert bucket.blob("big.bin").size == 1024 * 1024
```

## Ranged downloads

```python
@mock_gcp
def test_range():
    from google.cloud import storage

    client = storage.Client(project="p")
    bucket = client.create_bucket("b")
    bucket.blob("data.txt").upload_from_string("abcdefghij")

    assert bucket.blob("data.txt").download_as_bytes(start=2, end=4) == b"cde"
```

## Listing with prefix and delimiter

`delimiter="/"` gives you S3-style "folders" via `prefixes`:

```python
@mock_gcp
def test_list_prefixes():
    from google.cloud import storage

    client = storage.Client(project="p")
    bucket = client.create_bucket("b")
    for name in ["a/1.txt", "a/2.txt", "b/3.txt", "top.txt"]:
        bucket.blob(name).upload_from_string("x")

    it = client.list_blobs("b", prefix="a/", delimiter="/")
    assert [blob.name for blob in it] == ["a/1.txt", "a/2.txt"]
```

## Copy and rewrite

```python
@mock_gcp
def test_copy():
    from google.cloud import storage

    client = storage.Client(project="p")
    src = client.create_bucket("src")
    dst = client.create_bucket("dst")
    src.blob("orig.txt").upload_from_string("payload")

    src.copy_blob(src.blob("orig.txt"), dst, "copy.txt")
    assert dst.blob("copy.txt").download_as_text() == "payload"
```

## Inspecting state

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_inspect():
    from google.cloud import storage

    storage.Client(project="p").create_bucket("b")
    # Storage is global-namespace, so any project key returns the shared backend.
    assert "b" in get_backend("storage")["p"].buckets
```

## Bucket IAM and HMAC keys

Bucket IAM policies and project HMAC keys are supported:

```python
@mock_gcp
def test_iam_and_hmac():
    from google.cloud import storage

    client = storage.Client(project="p")
    bucket = client.create_bucket("b")

    policy = bucket.get_iam_policy()
    policy.bindings.append(
        {"role": "roles/storage.objectViewer", "members": {"allUsers"}}
    )
    bucket.set_iam_policy(policy)

    metadata, secret = client.create_hmac_key(
        service_account_email="svc@p.iam.gserviceaccount.com"
    )
    assert secret  # returned only on create
    metadata.state = "INACTIVE"
    metadata.update()
    metadata.delete()  # must be INACTIVE first, like real GCS
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete bucket | Supported |
| Bucket metadata (location, labels, versioning) | Partial |
| Upload: simple (`media`) | Supported |
| Upload: multipart | Supported |
| Upload: resumable (single + chunked) | Supported |
| Download (full) | Supported |
| Download with `Range` | Supported |
| Object metadata get / patch | Supported |
| List objects (prefix + delimiter) | Supported |
| Delete object | Supported |
| Copy / rewrite object | Supported |
| Bucket IAM policy (get / set / test permissions) | Supported |
| HMAC keys (create / list / get / update / delete) | Supported |
| Signed URLs, object ACLs, notifications | Planned |
