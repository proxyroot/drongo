# Cloud Scheduler

- **Client:** `google-cloud-scheduler` (`scheduler_v1.CloudSchedulerClient`)
- **Transport:** gRPC (the client default), forced to **REST** during a mock scope.
- **Backend:** per-project.

Use the **normal** client with no `transport` argument.

!!! note "run_job is the trigger"
    A mock can't tick a cron schedule, so nothing fires automatically on a job's
    `schedule`. Instead, `run_job` is the trigger: register an
    [executable handler](../executable-handlers.md) with `cloudscheduler.job_handler`
    and it runs (with the job's target) when the client calls `run_job`.

## Jobs

```python
from drongo import mock_gcp


@mock_gcp
def test_jobs():
    from google.cloud import scheduler_v1

    client = scheduler_v1.CloudSchedulerClient()
    parent = "projects/my-project/locations/us-central1"
    name = f"{parent}/jobs/nightly"

    client.create_job(
        request={
            "parent": parent,
            "job": {
                "name": name,
                "schedule": "0 2 * * *",
                "http_target": {
                    "uri": "https://example.com/run",
                    "http_method": scheduler_v1.HttpMethod.POST,
                    "body": b"payload",
                },
            },
        }
    )

    assert client.get_job(request={"name": name}).schedule == "0 2 * * *"
    client.pause_job(request={"name": name})
    client.resume_job(request={"name": name})
```

## Running a job (executable handler)

```python
from drongo import cloudscheduler, mock_gcp


@mock_gcp
def test_run():
    from google.cloud import scheduler_v1

    name = "projects/p/locations/us-central1/jobs/nightly"
    ran = []

    @cloudscheduler.job_handler(name)
    def handle(request):
        assert request.method == "POST"
        ran.append(request.body)

    client = scheduler_v1.CloudSchedulerClient()
    client.create_job(
        request={
            "parent": "projects/p/locations/us-central1",
            "job": {
                "name": name,
                "schedule": "* * * * *",
                "http_target": {
                    "uri": "https://x/y",
                    "http_method": scheduler_v1.HttpMethod.POST,
                    "body": b"go",
                },
            },
        }
    )

    client.run_job(request={"name": name})
    assert ran == [b"go"]
```

The handler receives a `SchedulerRequest` with `method` / `url` / `headers` /
`body` for HTTP targets, or `topic` / `data` for Pub/Sub targets. A raising
handler is recorded on the job's `last_error`, not raised to the caller.

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete job | Supported |
| Pause / resume | Supported |
| Update job | Supported |
| `run_job` (+ executable handler) | Supported |
| Actual cron scheduling / automatic firing | Planned (no real clock) |
| Retry config enforcement | Planned |
