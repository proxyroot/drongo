# Cloud Logging

- **Client:** `google-cloud-logging` (`logging.Client`)
- **Transport:** gRPC only. Like IAM, the underlying `LoggingServiceV2Client`
  ships no REST transport and honors no emulator env var, so drongo runs an
  in-process gRPC server and injects a transport into the default client.
- **Backend:** global namespace (entries carry their project in the log name).

Use the **normal** client with no `transport` argument.

!!! note "The library's diagnostic entry"
    On its first write, the google-cloud-logging library emits one
    diagnostic/instrumentation entry of its own (payload keyed
    `logging.googleapis.com/diagnostic`). drongo stores it faithfully, so filter
    it out if you assert on exact entry counts.

## Writing and reading entries

```python
from drongo import mock_gcp


@mock_gcp
def test_logging():
    import google.cloud.logging as logging

    client = logging.Client(project="my-project")
    logger = client.logger("app")

    logger.log_text("hello world", severity="INFO")
    logger.log_struct({"event": "signup", "user": 42})

    entries = list(client.list_entries(resource_names=["projects/my-project"]))
    payloads = [
        e.payload
        for e in entries
        if not (
            isinstance(e.payload, dict)
            and "logging.googleapis.com/diagnostic" in e.payload
        )
    ]
    assert payloads == ["hello world", {"event": "signup", "user": 42.0}]
```

`order_by=logging.DESCENDING` reverses the order (drongo orders by write
sequence). `client.logger("app").delete()` removes that log's entries.

## Inspecting state

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_inspect():
    import google.cloud.logging as logging

    logging.Client(project="p").logger("app").log_text("hi")
    entries = get_backend("logging")["p"].entries
    assert any(e.log_name == "projects/p/logs/app" for e in entries)
```

## Coverage

| Operation | Status |
| --- | --- |
| Write entries (`log_text` / `log_struct` / `log_proto`) | Supported |
| List entries (`list_entries`, by `resource_names`) | Supported |
| Ordering (`ASCENDING` / `DESCENDING`) | Supported |
| Delete a log (`logger.delete()`) | Supported |
| List logs (`ListLogs`) | Supported |
| Advanced filter language (`logName=`, `severity>=`, ...) | Planned (entries are returned unfiltered) |
| Sinks / exports (`ConfigServiceV2`) | Planned |
| Log-based metrics (`MetricsServiceV2`) | Planned |
| Tail (streaming) | Planned |
