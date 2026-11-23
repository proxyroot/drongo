"""Storage Transfer tests using the real storage_transfer_v1 client (forced REST)."""

from __future__ import annotations

import json

import pytest
from google.api_core import exceptions as gexc

pytest.importorskip("google.cloud.storage_transfer_v1")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"


def _client():
    from google.cloud import storage_transfer_v1

    return storage_transfer_v1.StorageTransferServiceClient()


def _job(client, description="nightly"):
    from google.cloud import storage_transfer_v1 as st

    spec = st.TransferSpec(
        gcs_data_source=st.GcsData(bucket_name="src"),
        gcs_data_sink=st.GcsData(bucket_name="dst"),
    )
    return client.create_transfer_job(
        request=st.CreateTransferJobRequest(
            transfer_job=st.TransferJob(
                description=description,
                project_id=PROJECT,
                transfer_spec=spec,
                status=st.TransferJob.Status.ENABLED,
            )
        )
    )


# -- google service account -------------------------------------------------


def test_google_service_account() -> None:
    from google.cloud import storage_transfer_v1 as st

    account = _client().get_google_service_account(
        request=st.GetGoogleServiceAccountRequest(project_id=PROJECT)
    )
    assert account.account_email.startswith(f"project-{PROJECT}@")


# -- transfer jobs ----------------------------------------------------------


def test_transfer_job_create_get_list_update_delete() -> None:
    from google.cloud import storage_transfer_v1 as st

    client = _client()
    job = _job(client)
    assert job.name.startswith("transferJobs/")
    assert job.status == st.TransferJob.Status.ENABLED

    got = client.get_transfer_job(
        request=st.GetTransferJobRequest(job_name=job.name, project_id=PROJECT)
    )
    assert got.description == "nightly"

    listed = list(
        client.list_transfer_jobs(
            request=st.ListTransferJobsRequest(
                filter=json.dumps({"projectId": PROJECT})
            )
        )
    )
    assert [j.name for j in listed] == [job.name]

    updated = client.update_transfer_job(
        request=st.UpdateTransferJobRequest(
            job_name=job.name,
            project_id=PROJECT,
            transfer_job=st.TransferJob(description="updated"),
            update_transfer_job_field_mask="description",
        )
    )
    assert updated.description == "updated"

    # Delete marks the job DELETED (Storage Transfer never removes jobs), so it
    # drops out of the list.
    client.delete_transfer_job(
        request=st.DeleteTransferJobRequest(job_name=job.name, project_id=PROJECT)
    )
    assert (
        list(
            client.list_transfer_jobs(
                request=st.ListTransferJobsRequest(
                    filter=json.dumps({"projectId": PROJECT})
                )
            )
        )
        == []
    )


def test_get_missing_transfer_job_not_found() -> None:
    from google.cloud import storage_transfer_v1 as st

    with pytest.raises(gexc.NotFound):
        _client().get_transfer_job(
            request=st.GetTransferJobRequest(
                job_name="transferJobs/999", project_id=PROJECT
            )
        )


# -- run + operations -------------------------------------------------------


def test_run_transfer_job_and_pause_resume_operation() -> None:
    from google.cloud import storage_transfer_v1 as st

    client = _client()
    job = _job(client)

    operation = client.run_transfer_job(
        request=st.RunTransferJobRequest(job_name=job.name, project_id=PROJECT)
    )
    assert operation.done()
    op_name = operation.metadata.name
    assert op_name.startswith("transferOperations/")

    # The operation is fetchable via the long-running Operations API.
    fetched = client.transport.operations_client.get_operation(op_name)
    assert fetched.done

    # Pause / resume flip its status without error.
    client.pause_transfer_operation(
        request=st.PauseTransferOperationRequest(name=op_name)
    )
    client.resume_transfer_operation(
        request=st.ResumeTransferOperationRequest(name=op_name)
    )


# -- agent pools ------------------------------------------------------------


def test_agent_pool_create_get_list_delete() -> None:
    from google.cloud import storage_transfer_v1 as st

    client = _client()
    pool = client.create_agent_pool(
        project_id=PROJECT,
        agent_pool_id="pool1",
        agent_pool=st.AgentPool(display_name="pool one"),
    )
    assert pool.name == f"projects/{PROJECT}/agentPools/pool1"

    assert client.get_agent_pool(name=pool.name).display_name == "pool one"
    assert [p.name for p in client.list_agent_pools(project_id=PROJECT)] == [pool.name]

    client.delete_agent_pool(name=pool.name)
    assert list(client.list_agent_pools(project_id=PROJECT)) == []
