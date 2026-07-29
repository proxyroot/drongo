# Cloud Tasks

- **Client:** `google-cloud-tasks`
- **Transport:** gRPC (the client default). drongo forces the client onto its
  **REST** transport for the mock scope (there is no emulator env var for Cloud
  Tasks).
- **Backend:** per-project.

Use the **normal** client with no `transport` argument.

!!! note "Error style under forced REST"
    Because the client is forced onto REST, errors surface as REST-style
    `google.api_core.exceptions`. A duplicate queue raises `Conflict` (not the
    gRPC `AlreadyExists`); a missing resource raises `NotFound`, which is the
    same for both transports.

## Queues

```python
from drongo import mock_gcp

PARENT = "projects/my-project/locations/us-central1"
QUEUE = f"{PARENT}/queues/emails"


@mock_gcp
def test_queue():
    from google.cloud import tasks_v2

    client = tasks_v2.CloudTasksClient()  # default, no transport arg
    client.create_queue(request={"parent": PARENT, "queue": {"name": QUEUE}})

    assert client.get_queue(request={"name": QUEUE}).name == QUEUE
```

## Tasks and dispatch

```python
@mock_gcp
def test_task():
    from google.cloud import tasks_v2

    client = tasks_v2.CloudTasksClient()
    client.create_queue(request={"parent": PARENT, "queue": {"name": QUEUE}})

    task = client.create_task(
        request={
            "parent": QUEUE,
            "task": {
                "http_request": {
                    "url": "https://example.com/handler",
                    "http_method": "POST",
                    "body": b"payload",
                }
            },
        }
    )
    assert task.dispatch_count == 0

    # run_task marks the task dispatched (there is no real network delivery).
    assert client.run_task(request={"name": task.name}).dispatch_count == 1
```

## Pause, resume, purge

```python
@mock_gcp
def test_queue_control():
    from google.cloud import tasks_v2

    client = tasks_v2.CloudTasksClient()
    client.create_queue(request={"parent": PARENT, "queue": {"name": QUEUE}})
    client.create_task(
        request={
            "parent": QUEUE,
            "task": {"http_request": {"url": "https://x/y", "http_method": "GET"}},
        }
    )

    client.pause_queue(request={"name": QUEUE})
    client.resume_queue(request={"name": QUEUE})

    client.purge_queue(request={"name": QUEUE})
    assert list(client.list_tasks(request={"parent": QUEUE})) == []
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete queue | Supported |
| Pause / resume / purge queue | Supported |
| Create / get / list / delete task | Supported |
| `run_task` (marks dispatched) | Supported |
| Actual task dispatch / delivery to targets | Planned (no real network I/O) |
| Retry config, rate limits, IAM | Planned |
