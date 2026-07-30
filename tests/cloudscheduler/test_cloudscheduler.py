"""Cloud Scheduler tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import cloudscheduler, get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"
NAME = f"{PARENT}/jobs/nightly"


def _client():
    from google.cloud import scheduler_v1

    return scheduler_v1.CloudSchedulerClient()


def _http_job(name=NAME, body=b"payload"):
    from google.cloud import scheduler_v1

    return {
        "name": name,
        "schedule": "0 2 * * *",
        "http_target": {
            "uri": "https://example.com/run",
            "http_method": scheduler_v1.HttpMethod.POST,
            "body": body,
        },
    }


def _create(client, job=None):
    return client.create_job(request={"parent": PARENT, "job": job or _http_job()})


# -- jobs -------------------------------------------------------------------


def test_create_and_get() -> None:
    client = _client()
    job = _create(client)
    assert job.name == NAME
    assert job.schedule == "0 2 * * *"
    assert client.get_job(request={"name": NAME}).name == NAME


def test_duplicate_conflicts() -> None:
    client = _client()
    _create(client)
    with pytest.raises(gexc.Conflict):
        _create(client)


def test_get_missing_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_job(request={"name": NAME})


def test_list_and_delete() -> None:
    client = _client()
    _create(client, _http_job(name=f"{PARENT}/jobs/a"))
    _create(client, _http_job(name=f"{PARENT}/jobs/b"))
    names = sorted(
        j.name.rsplit("/", 1)[-1] for j in client.list_jobs(request={"parent": PARENT})
    )
    assert names == ["a", "b"]

    client.delete_job(request={"name": f"{PARENT}/jobs/a"})
    with pytest.raises(gexc.NotFound):
        client.get_job(request={"name": f"{PARENT}/jobs/a"})


def test_pause_and_resume() -> None:
    client = _client()
    _create(client)
    assert client.pause_job(request={"name": NAME}).state.name == "PAUSED"
    assert client.resume_job(request={"name": NAME}).state.name == "ENABLED"


# -- executable handler -----------------------------------------------------


def test_run_job_invokes_handler() -> None:
    client = _client()
    _create(client)
    seen = []

    @cloudscheduler.job_handler(NAME)
    def handle(request) -> None:
        seen.append((request.method, request.url, request.body))

    client.run_job(request={"name": NAME})
    assert seen == [("POST", "https://example.com/run", b"payload")]


def test_run_without_handler_is_noop() -> None:
    client = _client()
    _create(client)
    # No handler registered: run_job just returns the job.
    assert client.run_job(request={"name": NAME}).name == NAME


def test_handler_failure_recorded_not_raised() -> None:
    client = _client()
    _create(client)

    @cloudscheduler.job_handler(NAME)
    def handle(request) -> None:
        raise ValueError("boom")

    client.run_job(request={"name": NAME})  # does not raise
    stored = get_backend("cloudscheduler")["test-project"].jobs[NAME]
    assert stored.last_error is not None
    assert "boom" in stored.last_error


def test_backend_is_inspectable() -> None:
    client = _client()
    _create(client)
    assert NAME in get_backend("cloudscheduler")["test-project"].jobs
