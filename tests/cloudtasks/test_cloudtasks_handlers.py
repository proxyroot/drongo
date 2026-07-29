"""Cloud Tasks executable handlers: dispatched tasks run real Python code."""

from __future__ import annotations

import pytest

from drongo import cloudtasks, get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"
QUEUE = f"{PARENT}/queues/emails"


def _client():
    from google.cloud import tasks_v2

    return tasks_v2.CloudTasksClient()


def _make_queue(client, name=QUEUE):
    client.create_queue(request={"parent": PARENT, "queue": {"name": name}})


def _task(body: bytes = b"payload"):
    return {
        "http_request": {
            "url": "https://example.com/handler",
            "http_method": "POST",
            "body": body,
        }
    }


def test_run_task_invokes_handler_with_request() -> None:
    client = _client()
    _make_queue(client)
    seen = []

    @cloudtasks.task_handler(QUEUE)
    def handle(request) -> None:
        seen.append((request.url, request.method, request.body))

    task = client.create_task(request={"parent": QUEUE, "task": _task(b"hi")})
    # Not dispatched yet on a queue whose handler was registered *before* create?
    # Registered before create, and queue is RUNNING, so it auto-delivered.
    assert seen == [("https://example.com/handler", "POST", b"hi")]
    assert task.dispatch_count == 1


def test_running_queue_auto_delivers_on_create() -> None:
    client = _client()
    _make_queue(client)
    count = []

    @cloudtasks.task_handler(QUEUE)
    def handle(request) -> None:
        count.append(1)

    client.create_task(request={"parent": QUEUE, "task": _task()})
    assert count == [1]


def test_paused_queue_does_not_auto_deliver() -> None:
    client = _client()
    _make_queue(client)
    count = []

    @cloudtasks.task_handler(QUEUE)
    def handle(request) -> None:
        count.append(1)

    client.pause_queue(request={"name": QUEUE})
    task = client.create_task(request={"parent": QUEUE, "task": _task()})
    assert count == []
    assert task.dispatch_count == 0

    # Explicit run_task still delivers.
    client.run_task(request={"name": task.name})
    assert count == [1]


def test_handler_failure_is_recorded_not_raised() -> None:
    client = _client()
    _make_queue(client)

    @cloudtasks.task_handler(QUEUE)
    def handle(request) -> None:
        raise ValueError("bad payload")

    # create_task (the producer) succeeds even though the consumer failed.
    task = client.create_task(request={"parent": QUEUE, "task": _task()})
    stored = get_backend("cloudtasks")["test-project"].queues[QUEUE].tasks[task.name]
    assert stored.last_error is not None
    assert "bad payload" in stored.last_error


def test_no_handler_leaves_task_undispatched() -> None:
    client = _client()
    _make_queue(client)
    task = client.create_task(request={"parent": QUEUE, "task": _task()})
    assert task.dispatch_count == 0
