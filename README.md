<!-- markdownlint-disable MD033 MD041 -->
<h1 align="center">🐦 drongo</h1>

<p align="center">
  <strong>Mock Google Cloud Platform services in your tests - the <a href="https://github.com/getmoto/moto">moto</a> for GCP.</strong>
</p>

<p align="center">
  <a href="https://github.com/proxyroot/drongo/actions/workflows/ci.yml"><img src="https://github.com/proxyroot/drongo/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/typed-yes-brightgreen.svg" alt="Typed">
</p>

---

`drongo` lets you test code that talks to Google Cloud **without touching the
network, running an emulator, or paying for real resources**. It stands up an
in-memory, in-process fake of GCP service APIs and transparently intercepts the
requests your google-cloud client libraries make.

If you've used [`moto`](https://github.com/getmoto/moto) for AWS, `drongo` will
feel immediately familiar - that's on purpose.

> **Why "drongo"?** `boto` (the AWS SDK) is named after the boto, the Amazon
> river dolphin, and `moto` mocks `boto`. The **drongo** is a bird famed for
> vocal mimicry: the fork-tailed drongo copies other animals' alarm calls to
> fool them into dropping their food. That is exactly what a mock does, so
> `drongo` does it for Google Cloud. 🐦

## Features

- 🎯 **One decorator** - `@mock_gcp` patches every supported service, just like `@mock_aws`.
- 🔌 **Flexible** - use it as a decorator, a context manager, a class decorator, or a `unittest.TestCase` mixin.
- 🧠 **In-memory & fast** - no Docker, no emulators, no sockets; tests run in milliseconds.
- 🌐 **Standalone server** - `drongo server` speaks real HTTP so SDKs in *any* language can point at it.
- 🧪 **pytest-native** - a `drongo` fixture is auto-registered on install.
- 🧩 **Extensible** - adding a service is `models.py` + `responses.py` + `urls.py`, the same shape as moto.
- ✅ **Typed** - ships `py.typed`, checked with mypy.

## Installation

```bash
pip install drongo
```

`drongo` does **not** depend on the google-cloud client libraries - you bring your
own (`google-cloud-storage`, `google-cloud-secret-manager`, …). It mocks
whatever you already use.

## Quickstart

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
without arguments - `drongo` supplies anonymous credentials and a default project
while a mock scope is active.

### Every way to invoke it (all like moto)

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

### pytest fixture

```python
def test_with_fixture(drongo):
    from google.cloud import storage

    storage.Client(project="p").create_bucket("b")

    # Inspect raw backend state, moto-style.
    assert "b" in drongo.backend("storage").buckets
```

### Secret Manager

Use the **normal** client; drongo forces it onto its REST transport for the
mock scope, so no code change is needed:

```python
from drongo import mock_gcp


@mock_gcp
def test_secret():
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()  # default, no transport arg
    secret = client.create_secret(
        request={
            "parent": "projects/my-project",
            "secret_id": "api-key",
            "secret": {"replication": {"automatic": {}}},
        }
    )
    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"s3cr3t"}}
    )

    accessed = client.access_secret_version(
        request={"name": f"{secret.name}/versions/latest"}
    )
    assert accessed.payload.data == b"s3cr3t"
```

### Pub/Sub

Pub/Sub is gRPC-first, so drongo runs an in-process gRPC emulator. Your code
uses the **normal** client with its default transport, unchanged:

```python
from drongo import mock_gcp


@mock_gcp
def test_pubsub():
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()  # default gRPC, no code change
    subscriber = pubsub_v1.SubscriberClient()
    topic = "projects/my-project/topics/orders"
    subscription = "projects/my-project/subscriptions/worker"

    publisher.create_topic(request={"name": topic})
    subscriber.create_subscription(request={"name": subscription, "topic": topic})

    publisher.publish(topic, b'{"id": 1}', kind="order").result()

    response = subscriber.pull(
        request={"subscription": subscription, "max_messages": 10}
    )
    assert response.received_messages[0].message.data == b'{"id": 1}'
    subscriber.acknowledge(
        request={
            "subscription": subscription,
            "ack_ids": [response.received_messages[0].ack_id],
        }
    )
```

## Standalone server mode

Run drongo as a real HTTP server - the same trick as `moto_server` - so
non-Python SDKs, or the google libraries in emulator mode, can use it:

```bash
drongo server --port 9090
export STORAGE_EMULATOR_HOST=http://localhost:9090
```

```python
from google.cloud import storage
from google.auth.credentials import AnonymousCredentials

client = storage.Client(project="p", credentials=AnonymousCredentials())
client.create_bucket("b")  # served by the drongo server over HTTP
```

## Supported services

| Service | Transport | Coverage |
| --- | --- | --- |
| **Cloud Storage** | JSON API (default) | buckets, objects, multipart/simple/resumable uploads, downloads (incl. Range), list w/ prefix & delimiter, copy/rewrite, metadata |
| **Secret Manager** | gRPC (default, forced to REST) | secrets, versions, access, enable/disable/destroy, list |
| **Pub/Sub** | gRPC (default, via emulator) | topics, subscriptions, publish fan-out, pull/ack, nack (modifyAckDeadline), list/delete |
| **BigQuery** | REST/JSON (default) | datasets, tables (with schema), streaming inserts (`insertAll`), read rows (`tabledata.list`), list/delete. Query *execution* not supported (needs a SQL engine) |
| **Cloud Tasks** | gRPC (default, forced to REST) | queues + tasks CRUD, `run_task`, purge, pause/resume, list |

More services are on the [roadmap](#roadmap). Adding one is intentionally
mechanical - see [`docs/contributing-a-service.md`](docs/contributing-a-service.md).

## How it works

`drongo` mirrors moto's architecture, adapted from AWS/botocore to GCP's
REST+JSON APIs:

- **`mock_gcp`** starts a reentrant controller that (a) activates the
  [`responses`](https://github.com/getsentry/responses) HTTP interception layer
  and (b) patches `google.auth.default` to return anonymous credentials.
- HTTP/REST services ship a **`models.py`** (in-memory state), a **`responses.py`**
  (a `BaseResponse` subclass with one method per API call), and a **`urls.py`**
  (`url_bases` + `url_paths`) - the same trio moto uses.
- gRPC-first services (Pub/Sub) can't be intercepted via HTTP, so drongo runs an
  in-process **gRPC emulator** backed by the same `models.py` and redirects the
  client with the standard `PUBSUB_EMULATOR_HOST` env var. Your code keeps its
  default transport; nothing changes.
- gRPC-default services that also ship a REST transport but have **no** emulator
  env var (Cloud Tasks) are served over REST: drongo transparently forces the
  client onto `transport="rest"` for the mock scope, so the default client still
  works unchanged.
- Backends are sharded through a **`BackendDict` keyed by project** (moto keys by
  account + region). Globally-namespaced resources like buckets share one
  backend, exactly as moto special-cases S3.
- The **standalone server** replays the HTTP route tables over a real socket.

See [`docs/architecture.md`](docs/architecture.md) for the full tour.

## Roadmap

- [x] Pub/Sub (in-process gRPC emulator)
- [x] BigQuery (resource + data management)
- [x] Cloud Tasks (forced REST)
- [ ] Cloud Run Jobs
- [ ] Firestore (gRPC emulator)
- [ ] Resource Manager (projects)
- [ ] Data seeding with Faker

Want one sooner? [Open an issue](https://github.com/proxyroot/drongo/issues/new/choose)
or contribute it - see below.

## Contributing

Contributions are very welcome! Adding a service is a great first PR. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`docs/contributing-a-service.md`](docs/contributing-a-service.md).

```bash
git clone https://github.com/proxyroot/drongo
cd drongo
make install   # editable install + dev tools
make check     # ruff + mypy + pytest
```

## License

[Apache License 2.0](LICENSE) - the same license as moto.

## Acknowledgements

`drongo` is heavily inspired by [`moto`](https://github.com/getmoto/moto) and owes
its design to that project. It is **not** affiliated with or endorsed by Google
or the moto maintainers.
