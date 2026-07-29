"""Cloud Tasks tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"
QUEUE = f"{PARENT}/queues/q"


def _client():
    from google.cloud import tasks_v2

    return tasks_v2.CloudTasksClient()


def _http_task():
    return {
        "http_request": {
            "url": "https://example.com/x",
            "http_method": "POST",
            "body": b"hi",
        }
    }


def _make_queue(client, name=QUEUE):
    client.create_queue(request={"parent": PARENT, "queue": {"name": name}})


# -- queues -----------------------------------------------------------------


def test_create_and_get_queue() -> None:
    client = _client()
    _make_queue(client)
    assert client.get_queue(request={"name": QUEUE}).name == QUEUE


def test_duplicate_queue_conflicts() -> None:
    client = _client()
    _make_queue(client)
    # Forced REST surfaces HTTP 409 as Conflict (gRPC would be AlreadyExists).
    with pytest.raises(gexc.Conflict):
        _make_queue(client)


def test_get_missing_queue_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_queue(request={"name": QUEUE})


def test_list_and_delete_queues() -> None:
    client = _client()
    _make_queue(client, f"{PARENT}/queues/a")
    _make_queue(client, f"{PARENT}/queues/b")
    names = sorted(
        q.name.rsplit("/", 1)[-1]
        for q in client.list_queues(request={"parent": PARENT})
    )
    assert names == ["a", "b"]

    client.delete_queue(request={"name": f"{PARENT}/queues/a"})
    remaining = [
        q.name.rsplit("/", 1)[-1]
        for q in client.list_queues(request={"parent": PARENT})
    ]
    assert remaining == ["b"]


def test_pause_and_resume_queue() -> None:
    client = _client()
    _make_queue(client)
    assert client.pause_queue(request={"name": QUEUE}).state.name == "PAUSED"
    assert client.resume_queue(request={"name": QUEUE}).state.name == "RUNNING"


# -- tasks ------------------------------------------------------------------


def test_create_task_and_list() -> None:
    client = _client()
    _make_queue(client)
    task = client.create_task(request={"parent": QUEUE, "task": _http_task()})
    assert task.name.startswith(f"{QUEUE}/tasks/")
    assert [t.name for t in client.list_tasks(request={"parent": QUEUE})] == [task.name]


def test_create_task_missing_queue_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().create_task(request={"parent": QUEUE, "task": _http_task()})


def test_run_task_increments_dispatch_count() -> None:
    client = _client()
    _make_queue(client)
    task = client.create_task(request={"parent": QUEUE, "task": _http_task()})
    assert task.dispatch_count == 0
    assert client.run_task(request={"name": task.name}).dispatch_count == 1


def test_delete_task() -> None:
    client = _client()
    _make_queue(client)
    task = client.create_task(request={"parent": QUEUE, "task": _http_task()})
    client.delete_task(request={"name": task.name})
    with pytest.raises(gexc.NotFound):
        client.get_task(request={"name": task.name})


def test_purge_queue_clears_tasks() -> None:
    client = _client()
    _make_queue(client)
    client.create_task(request={"parent": QUEUE, "task": _http_task()})
    client.purge_queue(request={"name": QUEUE})
    assert list(client.list_tasks(request={"parent": QUEUE})) == []


def test_backend_is_inspectable() -> None:
    client = _client()
    _make_queue(client)
    assert QUEUE in get_backend("cloudtasks")["test-project"].queues
