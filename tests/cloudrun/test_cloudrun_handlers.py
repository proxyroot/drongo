"""Cloud Run Jobs executable handlers: run_job invokes real Python code."""

from __future__ import annotations

import pytest

from drongo import cloudrun, get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"
NAME = f"{PARENT}/jobs/batch"


def _jobs():
    from google.cloud import run_v2

    return run_v2.JobsClient()


def _create(client, job_id: str = "batch"):
    from google.cloud import run_v2

    job = run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/test/img")]
            )
        )
    )
    return client.create_job(
        request={"parent": PARENT, "job": job, "job_id": job_id}
    ).result(timeout=10)


def test_run_job_invokes_handler() -> None:
    client = _jobs()
    _create(client)
    ran = []

    @cloudrun.job_handler(NAME)
    def handler() -> None:
        ran.append("ran")

    execution = client.run_job(request={"name": NAME}).result(timeout=10)

    assert ran == ["ran"]
    assert execution.succeeded_count == 1
    assert execution.failed_count == 0


def test_handler_exception_marks_execution_failed() -> None:
    client = _jobs()
    _create(client)

    @cloudrun.job_handler(NAME)
    def handler() -> None:
        raise RuntimeError("boom")

    execution = client.run_job(request={"name": NAME}).result(timeout=10)

    assert execution.succeeded_count == 0
    assert execution.failed_count == 1
    condition = execution.conditions[0]
    assert condition.type == "Completed"
    assert "boom" in condition.message


def test_no_handler_is_a_successful_noop() -> None:
    client = _jobs()
    _create(client)
    execution = client.run_job(request={"name": NAME}).result(timeout=10)
    assert execution.succeeded_count == 1
    assert execution.failed_count == 0


def test_register_via_backend_method() -> None:
    client = _jobs()
    _create(client)
    ran = []
    get_backend("cloudrun")["test-project"].register_handler(
        NAME, lambda: ran.append("x")
    )

    client.run_job(request={"name": NAME}).result(timeout=10)
    assert ran == ["x"]
