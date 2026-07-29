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

<p align="center">
  <strong><a href="https://drongo.proxyroot.com">Documentation</a></strong>
</p>

---

`drongo` lets you test code that talks to Google Cloud **without touching the
network, running an emulator, or paying for real resources**. It stands up an
in-memory, in-process fake of GCP service APIs and transparently intercepts the
requests your google-cloud client libraries make.

If you've used [`moto`](https://github.com/getmoto/moto) for AWS, `drongo` will
feel immediately familiar - that's on purpose.

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

    bucket.blob("hello.txt").upload_from_string("hello drongo")

    assert bucket.blob("hello.txt").download_as_text() == "hello drongo"
    assert [b.name for b in client.list_blobs("my-bucket")] == ["hello.txt"]
```

No credentials, no network, no emulator. `storage.Client()` works with or without
arguments - `drongo` supplies anonymous credentials and a default project while a
mock scope is active. It also works as a called decorator, a context manager, a
class decorator, or a `unittest.TestCase` mixin, and ships an auto-registered
`drongo` pytest fixture - see the
**[Quickstart guide](https://drongo.proxyroot.com/quickstart/)**.

## Features

- 🎯 **One decorator** - `@mock_gcp` patches every supported service, just like `@mock_aws`.
- 🔌 **Flexible** - decorator, context manager, class decorator, or `unittest.TestCase` mixin.
- 🧠 **In-memory & fast** - no Docker, no emulators, no sockets; tests run in milliseconds.
- 🧬 **Default clients, unchanged** - drongo handles gRPC-first services behind the scenes.
- 🏃 **Runs your code** - opt-in [executable handlers](https://drongo.proxyroot.com/executable-handlers/) actually run your Python when a job runs, a task dispatches, or a message publishes.
- 🌐 **Standalone server** - `drongo server` speaks real HTTP so SDKs in *any* language can point at it.
- 🧪 **pytest-native** - a `drongo` fixture is auto-registered on install.
- 🧩 **Extensible** - adding a service is `models.py` + `responses.py` + `urls.py`, the same shape as moto.
- ✅ **Typed** - ships `py.typed`, checked with mypy.

## Supported services

| Service | Transport | Docs |
| --- | --- | --- |
| **Cloud Storage** | JSON API (default) | [guide](https://drongo.proxyroot.com/services/storage/) |
| **Secret Manager** | gRPC (default, forced to REST) | [guide](https://drongo.proxyroot.com/services/secret-manager/) |
| **Pub/Sub** | gRPC (default, via emulator) | [guide](https://drongo.proxyroot.com/services/pubsub/) |
| **BigQuery** | REST/JSON (default) | [guide](https://drongo.proxyroot.com/services/bigquery/) |
| **Cloud Tasks** | gRPC (default, forced to REST) | [guide](https://drongo.proxyroot.com/services/cloud-tasks/) |
| **Cloud Run Jobs** | gRPC (default, forced to REST) | [guide](https://drongo.proxyroot.com/services/cloud-run-jobs/) |
| **Resource Manager** | gRPC (default, forced to REST) | [guide](https://drongo.proxyroot.com/services/resource-manager/) |
| **Firestore** | gRPC (default, via emulator) | [guide](https://drongo.proxyroot.com/services/firestore/) |
| **IAM & Service Accounts** | gRPC only (via injected transport) | [guide](https://drongo.proxyroot.com/services/iam/) |
| **Cloud Logging** | gRPC only (via injected transport) | [guide](https://drongo.proxyroot.com/services/cloud-logging/) |

Full capability matrix: **[Supported services](https://drongo.proxyroot.com/supported-services/)**.
You can also fill the mocks with realistic
**[Faker data](https://drongo.proxyroot.com/seeding/)**, or run drongo as a
**[standalone HTTP server](https://drongo.proxyroot.com/server/)** for non-Python SDKs.

## How it works

`drongo` mirrors moto's architecture, adapted from AWS/botocore to GCP's
REST+JSON APIs: HTTP services ship a `models.py` / `responses.py` / `urls.py`
trio behind the [`responses`](https://github.com/getsentry/responses)
interception layer, gRPC-first services run against an in-process emulator or a
forced-REST transport, and state is sharded through a `BackendDict` keyed by
project. See the
**[Architecture tour](https://drongo.proxyroot.com/architecture/)** for the full
picture.

## Roadmap

**Available (8 services):** Cloud Storage, Secret Manager, Pub/Sub, BigQuery,
Cloud Tasks, Cloud Run Jobs, Resource Manager, Firestore - plus executable
handlers, Faker seeding, and a standalone server.

**Next up:** Cloud Logging, Cloud KMS, IAM / Service Accounts, Cloud Scheduler,
Cloud Functions, Datastore mode. See the full, tiered
**[roadmap](https://drongo.proxyroot.com/roadmap/)** (services + capabilities,
and how drongo compares to moto).

Want one sooner? [Open an issue](https://github.com/proxyroot/drongo/issues/new/choose)
or contribute it.

## Contributing

Contributions are very welcome! Adding a service is a great first PR. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[contributing-a-service guide](https://drongo.proxyroot.com/contributing-a-service/).

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
