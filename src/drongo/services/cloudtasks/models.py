"""In-memory models for Google Cloud Tasks.

Like moto's SQS backend: queues hold tasks. ``run_task`` marks a task dispatched
(it does not actually deliver the HTTP/App Engine request, which would mean real
network I/O). Resources are stored by full resource name.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class TaskRequest:
    """The task's HTTP target, as delivered to a registered handler.

    ``body`` is decoded to ``bytes`` (the REST API base64-encodes it on the
    wire). ``payload`` is the full raw target dict if you need fields not lifted
    out here.
    """

    name: str
    url: str
    method: str
    headers: dict[str, str]
    body: bytes
    payload: dict[str, Any]


#: A task handler receives the dispatched task's HTTP target.
TaskHandler = Callable[[TaskRequest], Any]

#: Cloud Tasks HttpMethod enum. The REST transport may send the method as its
#: integer value, so normalize it back to the familiar name for handlers.
_HTTP_METHODS = {
    0: "HTTP_METHOD_UNSPECIFIED",
    1: "POST",
    2: "GET",
    3: "HEAD",
    4: "PUT",
    5: "DELETE",
    6: "PATCH",
    7: "OPTIONS",
}


def _method_name(raw: Any) -> str:
    if isinstance(raw, bool):  # guard: bool is an int subclass
        return "POST"
    if isinstance(raw, int):
        return _HTTP_METHODS.get(raw, "POST")
    if isinstance(raw, str) and raw.isdigit():
        return _HTTP_METHODS.get(int(raw), "POST")
    return str(raw or "POST")


@dataclass
class Task:
    """A queued task (its target request is stored)."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    schedule_time: str = ""
    create_time: str = field(default_factory=_now)
    dispatch_count: int = 0
    last_error: str | None = None

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "name": self.name,
            "createTime": self.create_time,
            "dispatchCount": self.dispatch_count,
            "view": "BASIC",
        }
        if self.schedule_time:
            resource["scheduleTime"] = self.schedule_time
        # Echo the target request (httpRequest / appEngineHttpRequest / etc.).
        resource.update(self.payload)
        return resource


@dataclass
class Queue:
    """A Cloud Tasks queue and the tasks it holds."""

    name: str
    state: str = "RUNNING"
    tasks: dict[str, Task] = field(default_factory=dict)

    def to_resource(self) -> dict[str, Any]:
        return {"name": self.name, "state": self.state}


class CloudTasksBackend(BaseBackend):
    """In-memory Cloud Tasks state for a single project."""

    def setup(self) -> None:
        self.queues: dict[str, Queue] = {}
        self.handlers: dict[str, TaskHandler] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def register_handler(self, queue_name: str, handler: TaskHandler) -> None:
        """Bind a callable to a queue; dispatched tasks are delivered to it."""
        self.handlers[queue_name] = handler

    def _dispatch(self, queue: Queue, task: Task) -> None:
        """Deliver ``task`` to the queue's handler, recording any failure.

        A real queue does not surface a consumer's failure to the producer, so a
        raising handler is recorded on ``task.last_error`` rather than propagated.
        """
        handler = self.handlers.get(queue.name)
        task.dispatch_count += 1
        if handler is None:
            return
        target = task.payload.get("httpRequest") or task.payload.get(
            "appEngineHttpRequest", {}
        )
        body = target.get("body")
        request = TaskRequest(
            name=task.name,
            url=target.get("url", ""),
            method=_method_name(target.get("httpMethod")),
            headers=dict(target.get("headers", {})),
            body=base64.b64decode(body) if body else b"",
            payload=task.payload,
        )
        try:
            handler(request)
        except Exception as exc:  # noqa: BLE001 - recorded, not raised to producer
            task.last_error = f"{type(exc).__name__}: {exc}"

    # -- queues ------------------------------------------------------------

    def create_queue(self, name: str) -> Queue:
        if name in self.queues:
            raise exceptions.already_exists(f"Queue already exists: {name}")
        queue = Queue(name=name)
        self.queues[name] = queue
        return queue

    def get_queue(self, name: str) -> Queue:
        try:
            return self.queues[name]
        except KeyError:
            raise exceptions.not_found(f"Queue does not exist: {name}")

    def list_queues(self, parent: str) -> list[Queue]:
        prefix = f"{parent}/queues/"
        return [self.queues[n] for n in sorted(self.queues) if n.startswith(prefix)]

    def delete_queue(self, name: str) -> None:
        self.get_queue(name)
        del self.queues[name]

    def purge_queue(self, name: str) -> Queue:
        queue = self.get_queue(name)
        queue.tasks.clear()
        return queue

    def set_queue_state(self, name: str, state: str) -> Queue:
        queue = self.get_queue(name)
        queue.state = state
        return queue

    # -- tasks -------------------------------------------------------------

    def create_task(self, queue_name: str, task: dict[str, Any]) -> Task:
        queue = self.get_queue(queue_name)
        name = task.get("name") or f"{queue_name}/tasks/{self._next()}"
        if name in queue.tasks:
            raise exceptions.already_exists(f"Task already exists: {name}")
        payload = {
            key: value
            for key, value in task.items()
            if key not in ("name", "scheduleTime")
        }
        created = Task(
            name=name,
            payload=payload,
            schedule_time=task.get("scheduleTime", ""),
        )
        queue.tasks[name] = created
        # A running queue with a registered handler delivers immediately, so a
        # producer-only test (create_task, no run_task) still exercises the
        # consumer. Without a handler nothing dispatches (dispatch_count stays 0).
        if queue.state == "RUNNING" and queue.name in self.handlers:
            self._dispatch(queue, created)
        return created

    def get_task(self, queue_name: str, name: str) -> Task:
        queue = self.get_queue(queue_name)
        try:
            return queue.tasks[name]
        except KeyError:
            raise exceptions.not_found(f"Task does not exist: {name}")

    def list_tasks(self, queue_name: str) -> list[Task]:
        queue = self.get_queue(queue_name)
        return [queue.tasks[n] for n in sorted(queue.tasks)]

    def delete_task(self, queue_name: str, name: str) -> None:
        queue = self.get_queue(queue_name)
        if name not in queue.tasks:
            raise exceptions.not_found(f"Task does not exist: {name}")
        del queue.tasks[name]

    def run_task(self, queue_name: str, name: str) -> Task:
        task = self.get_task(queue_name, name)
        self._dispatch(self.queues[queue_name], task)
        return task


#: Project-keyed backends, inspectable via ``get_backend("cloudtasks")[project]``.
cloudtasks_backends: BackendDict[CloudTasksBackend] = BackendDict(
    CloudTasksBackend, "cloudtasks"
)
