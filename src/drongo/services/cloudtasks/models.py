"""In-memory models for Google Cloud Tasks.

Like moto's SQS backend: queues hold tasks. ``run_task`` marks a task dispatched
(it does not actually deliver the HTTP/App Engine request, which would mean real
network I/O). Resources are stored by full resource name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Task:
    """A queued task (its target request is stored, never dispatched)."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    schedule_time: str = ""
    create_time: str = field(default_factory=_now)
    dispatch_count: int = 0

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
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

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
        task.dispatch_count += 1
        return task


#: Project-keyed backends, inspectable via ``get_backend("cloudtasks")[project]``.
cloudtasks_backends: BackendDict[CloudTasksBackend] = BackendDict(
    CloudTasksBackend, "cloudtasks"
)
