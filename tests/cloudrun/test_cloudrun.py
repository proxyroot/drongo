"""Cloud Run Jobs tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"


def _jobs():
    from google.cloud import run_v2

    return run_v2.JobsClient()


def _executions():
    from google.cloud import run_v2

    return run_v2.ExecutionsClient()


def _job_obj():
    from google.cloud import run_v2

    return run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/test/img")]
            )
        )
    )


def _create(client, job_id: str = "batch"):
    return client.create_job(
        request={"parent": PARENT, "job": _job_obj(), "job_id": job_id}
    ).result(timeout=10)


def test_create_and_get_job() -> None:
    client = _jobs()
    created = _create(client)
    assert created.name == f"{PARENT}/jobs/batch"
    assert client.get_job(request={"name": f"{PARENT}/jobs/batch"}).name == created.name


def test_duplicate_job_conflicts() -> None:
    client = _jobs()
    _create(client)
    with pytest.raises(gexc.Conflict):
        _create(client)


def test_get_missing_job_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _jobs().get_job(request={"name": f"{PARENT}/jobs/ghost"})


def test_list_jobs() -> None:
    client = _jobs()
    _create(client, "a")
    _create(client, "b")
    names = sorted(
        j.name.rsplit("/", 1)[-1] for j in client.list_jobs(request={"parent": PARENT})
    )
    assert names == ["a", "b"]


def test_run_job_creates_execution() -> None:
    jobs, executions = _jobs(), _executions()
    _create(jobs)
    execution = jobs.run_job(request={"name": f"{PARENT}/jobs/batch"}).result(
        timeout=10
    )
    assert execution.name.startswith(f"{PARENT}/jobs/batch/executions/")

    listed = list(
        executions.list_executions(request={"parent": f"{PARENT}/jobs/batch"})
    )
    assert len(listed) == 1
    assert (
        executions.get_execution(request={"name": execution.name}).name
        == execution.name
    )


def test_delete_job() -> None:
    client = _jobs()
    _create(client)
    client.delete_job(request={"name": f"{PARENT}/jobs/batch"}).result(timeout=10)
    with pytest.raises(gexc.NotFound):
        client.get_job(request={"name": f"{PARENT}/jobs/batch"})


def test_backend_is_inspectable() -> None:
    client = _jobs()
    _create(client)
    assert f"{PARENT}/jobs/batch" in get_backend("cloudrun")["test-project"].jobs
