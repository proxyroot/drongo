# Storage Transfer

- **Client:** `google-cloud-storage-transfer` (`storage_transfer_v1.StorageTransferServiceClient`)
- **Transport:** gRPC (the client default), forced to REST during a mock scope.
  Storage Transfer has no emulator env var, so drongo forces the client onto its
  REST transport and serves it from the HTTP layer.
- **Backend:** one global namespace (transfer-job names are globally unique).

Use the normal client with no `transport` argument. Storage Transfer's methods
take `request=` objects (they have no flattened keyword helpers).

Covers transfer jobs (create / get / list / update / delete + run), the transfer
operations that a run produces (get / pause / resume / cancel), the Google-managed
service account, and agent pools.

## Transfer jobs and running them

```python
import json

from drongo import mock_gcp


@mock_gcp
def test_transfer_jobs():
    from google.cloud import storage_transfer_v1 as st

    project = "my-project"
    client = st.StorageTransferServiceClient()

    job = client.create_transfer_job(
        request=st.CreateTransferJobRequest(
            transfer_job=st.TransferJob(
                description="nightly",
                project_id=project,
                transfer_spec=st.TransferSpec(
                    gcs_data_source=st.GcsData(bucket_name="src"),
                    gcs_data_sink=st.GcsData(bucket_name="dst"),
                ),
                status=st.TransferJob.Status.ENABLED,
            )
        )
    )

    listed = client.list_transfer_jobs(
        request=st.ListTransferJobsRequest(filter=json.dumps({"projectId": project}))
    )
    assert [j.name for j in listed] == [job.name]

    # Running the job returns a long-running transfer operation (done here).
    operation = client.run_transfer_job(
        request=st.RunTransferJobRequest(job_name=job.name, project_id=project)
    )
    op_name = operation.metadata.name
    client.pause_transfer_operation(
        request=st.PauseTransferOperationRequest(name=op_name)
    )
    client.resume_transfer_operation(
        request=st.ResumeTransferOperationRequest(name=op_name)
    )
```

`delete_transfer_job` marks the job `DELETED` (Storage Transfer never removes
jobs), so it drops out of `list_transfer_jobs`. Missing jobs raise
`google.api_core.exceptions.NotFound`.

## Coverage

| Operation | Status |
| --- | --- |
| Transfer jobs: create / get / list / update / delete | Supported |
| Run transfer job (LRO) + operation get / pause / resume / cancel | Supported |
| Google service account: get | Supported |
| Agent pools: create / get / list / update / delete | Supported |
| Actual data movement between buckets | Planned (no real I/O) |
