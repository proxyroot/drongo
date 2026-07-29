# drongo

**Mock Google Cloud Platform services in your tests. The [moto](https://github.com/getmoto/moto) for GCP.**

`drongo` lets you test code that talks to Google Cloud **without touching the
network, running an emulator, or paying for real resources**. It stands up an
in-memory, in-process fake of GCP service APIs and transparently intercepts the
requests your `google-cloud-*` client libraries make.

If you've used [`moto`](https://github.com/getmoto/moto) for AWS, `drongo` will
feel immediately familiar. That's on purpose.

```python
from drongo import mock_gcp


@mock_gcp
def test_upload_download():
    from google.cloud import storage

    client = storage.Client(project="my-project")
    bucket = client.create_bucket("my-bucket")
    bucket.blob("hello.txt").upload_from_string("hello drongo")

    assert bucket.blob("hello.txt").download_as_text() == "hello drongo"
```

No credentials, no network, no emulator, no Docker.

## Why "drongo"?

`boto` (the AWS SDK) is named after the boto, the Amazon river dolphin, and
`moto` mocks `boto`. The **drongo** is a bird famed for vocal mimicry: the
fork-tailed drongo copies other animals' alarm calls to fool them into dropping
their food. That is exactly what a mock does, so `drongo` does it for Google
Cloud.

## Highlights

- **One decorator.** `@mock_gcp` patches every supported service, just like `@mock_aws`.
- **Flexible.** Decorator, context manager, class decorator, or `unittest.TestCase` mixin.
- **In-memory and fast.** No Docker, no emulators, no sockets. Tests run in milliseconds.
- **Default clients, unchanged.** Your code uses its normal client, with its normal
  transport. drongo handles gRPC-first services behind the scenes.
- **Runs your code.** Opt-in [executable handlers](executable-handlers.md) actually
  run your Python when a job runs, a task dispatches, or a message publishes.
- **Standalone server.** `drongo server` speaks real HTTP so SDKs in *any* language can point at it.
- **pytest-native.** A `drongo` fixture is auto-registered on install.
- **Typed.** Ships `py.typed`, checked with mypy.

## Where to next

- New here? Start with the [Quickstart](quickstart.md).
- Look up a specific service under **Services** in the sidebar.
- Fill your mocks with realistic data using [Faker](seeding.md).
- Point non-Python SDKs at the [standalone server](server.md).
- Curious how it works, or want to add a service? See
  [Architecture](architecture.md) and [Contributing a service](contributing-a-service.md).

## Installation

```bash
pip install drongo
```

`drongo` does **not** depend on the google-cloud client libraries. You bring your
own (`google-cloud-storage`, `google-cloud-secret-manager`, and so on). It mocks
whatever you already use.

## License

[Apache License 2.0](https://github.com/proxyroot/drongo/blob/main/LICENSE), the
same license as moto. `drongo` is heavily inspired by moto and is **not**
affiliated with or endorsed by Google or the moto maintainers.
