# Vertex AI

- **Client:** `google-cloud-aiplatform` (`aiplatform_v1` service clients)
- **Transport:** gRPC (the client default), forced to REST during a mock scope.
  Vertex AI has no emulator env var, so drongo forces the service clients onto
  their REST transport and serves them from the HTTP layer.
- **Backend:** per-project.

Use the normal clients with no `transport` argument. Vertex AI uses regional
endpoints, so pass the region the same way you would against the real API.

Scoped to the **control plane**: datasets, endpoints, models, custom jobs, and
batch prediction jobs. Mutations that Vertex models as long-running operations
(create/delete dataset, endpoint, model) complete synchronously, so `.result()`
returns immediately. Jobs are created and returned directly.

## Datasets, endpoints, models

```python
from drongo import mock_gcp
from google.api_core.client_options import ClientOptions


@mock_gcp
def test_vertex_control_plane():
    from google.cloud import aiplatform_v1

    location = "us-central1"
    parent = f"projects/my-project/locations/{location}"
    opts = ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")

    datasets = aiplatform_v1.DatasetServiceClient(client_options=opts)
    dataset = datasets.create_dataset(
        parent=parent,
        dataset=aiplatform_v1.Dataset(
            display_name="my-ds", metadata_schema_uri="gs://schema"
        ),
    ).result()  # the create LRO completes synchronously

    assert datasets.get_dataset(name=dataset.name).display_name == "my-ds"
    assert [d.display_name for d in datasets.list_datasets(parent=parent)] == ["my-ds"]

    endpoints = aiplatform_v1.EndpointServiceClient(client_options=opts)
    endpoint = endpoints.create_endpoint(
        parent=parent, endpoint=aiplatform_v1.Endpoint(display_name="my-ep")
    ).result()

    models = aiplatform_v1.ModelServiceClient(client_options=opts)
    uploaded = models.upload_model(
        parent=parent, model=aiplatform_v1.Model(display_name="my-model")
    ).result()
    assert models.get_model(name=uploaded.model).display_name == "my-model"
```

## Custom and batch prediction jobs

```python
@mock_gcp
def test_vertex_jobs():
    from google.cloud import aiplatform_v1

    location = "us-central1"
    parent = f"projects/my-project/locations/{location}"
    opts = ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
    jobs = aiplatform_v1.JobServiceClient(client_options=opts)

    job = jobs.create_custom_job(
        parent=parent,
        custom_job=aiplatform_v1.CustomJob(
            display_name="train",
            job_spec=aiplatform_v1.CustomJobSpec(worker_pool_specs=[]),
        ),
    )
    assert jobs.get_custom_job(name=job.name).display_name == "train"

    jobs.cancel_custom_job(name=job.name)
    assert (
        jobs.get_custom_job(name=job.name).state
        == aiplatform_v1.JobState.JOB_STATE_CANCELLED
    )
```

Missing resources raise `google.api_core.exceptions.NotFound`.

## Coverage

| Operation | Status |
| --- | --- |
| Datasets: create / get / list / delete (LRO) | Supported |
| Endpoints: create / get / list / delete (LRO) | Supported |
| Models: upload / get / list / delete (LRO) | Supported |
| Custom jobs: create / get / list / cancel / delete | Supported |
| Batch prediction jobs: create / get / list / cancel / delete | Supported |
| Deploy / undeploy model, predict / online prediction | Planned |
| Pipeline jobs, tuning jobs, feature store, index | Planned |
