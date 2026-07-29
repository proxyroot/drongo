# Cloud Run Jobs

- **Client:** `google-cloud-run` (`run_v2.JobsClient` / `run_v2.ExecutionsClient`)
- **Transport:** gRPC (the client default). drongo forces the client onto its
  **REST** transport for the mock scope.
- **Backend:** per-project.

Use the **normal** clients with no `transport` argument.

!!! note "Long-running operations complete synchronously"
    Cloud Run's mutating calls (`create_job`, `run_job`, `delete_job`) return a
    **long-running operation** (LRO). drongo completes each one synchronously and
    returns a *done* operation, so `.result()` returns immediately with the final
    resource. There is no real container execution. Errors surface as REST-style
    exceptions (a duplicate job raises `Conflict`).

## Create and run a job

`create_job` and `run_job` return an LRO; call `.result()` to get the resource:

```python
from drongo import mock_gcp

PARENT = "projects/my-project/locations/us-central1"


@mock_gcp
def test_run_job():
    from google.cloud import run_v2

    jobs = run_v2.JobsClient()  # default, no transport arg
    executions = run_v2.ExecutionsClient()

    job = run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/my-project/batch")]
            )
        )
    )
    created = jobs.create_job(
        request={"parent": PARENT, "job": job, "job_id": "nightly"}
    ).result(timeout=10)
    assert created.name == f"{PARENT}/jobs/nightly"

    # Running the job creates an execution.
    execution = jobs.run_job(request={"name": f"{PARENT}/jobs/nightly"}).result(
        timeout=10
    )
    assert execution.name.startswith(f"{PARENT}/jobs/nightly/executions/")
```

## Executions

```python
@mock_gcp
def test_executions():
    from google.cloud import run_v2

    jobs = run_v2.JobsClient()
    executions = run_v2.ExecutionsClient()
    job = run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/p/img")]
            )
        )
    )
    jobs.create_job(request={"parent": PARENT, "job": job, "job_id": "batch"}).result()
    jobs.run_job(request={"name": f"{PARENT}/jobs/batch"}).result()

    listed = list(
        executions.list_executions(request={"parent": f"{PARENT}/jobs/batch"})
    )
    assert len(listed) == 1
    fetched = executions.get_execution(request={"name": listed[0].name})
    assert fetched.name == listed[0].name
```

## Delete a job

```python
@mock_gcp
def test_delete_job():
    from google.cloud import run_v2
    from google.api_core import exceptions as gexc

    jobs = run_v2.JobsClient()
    job = run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/p/img")]
            )
        )
    )
    jobs.create_job(request={"parent": PARENT, "job": job, "job_id": "batch"}).result()

    jobs.delete_job(request={"name": f"{PARENT}/jobs/batch"}).result(timeout=10)
    try:
        jobs.get_job(request={"name": f"{PARENT}/jobs/batch"})
    except gexc.NotFound:
        pass
```

## Run your actual code

Register a Python function for a job and drongo runs it when `run_job` is called
(a raising handler marks the execution failed). See
[Executable handlers](../executable-handlers.md).

```python
from drongo import cloudrun


@cloudrun.job_handler("projects/p/locations/us-central1/jobs/nightly")
def nightly(): ...  # real work; runs on run_job
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete job | Supported |
| `run_job` (creates an execution) | Supported |
| Executable handler (`run_job` runs your function) | Supported |
| Executions: get / list / delete | Supported |
| Long-running operations (`.result()`) | Supported (completed synchronously) |
| Actual container execution | Planned (no real compute) |
| Cloud Run *services* (serving), revisions, traffic | Planned |
