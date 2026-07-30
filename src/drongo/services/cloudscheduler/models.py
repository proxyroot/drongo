"""In-memory models for Google Cloud Scheduler.

Cloud Scheduler defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST and serves it over HTTP. A mock can't tick a cron schedule, so
``run_job`` is the trigger: if a handler is registered for the job, drongo invokes
it with the job's target (HTTP or Pub/Sub), mirroring Cloud Tasks.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = [
    "Job",
    "SchedulerBackend",
    "SchedulerRequest",
    "cloudscheduler_backends",
]

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


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _method_name(raw: Any) -> str:
    if isinstance(raw, bool):
        return "POST"
    if isinstance(raw, int):
        return _HTTP_METHODS.get(raw, "POST")
    if isinstance(raw, str) and raw.isdigit():
        return _HTTP_METHODS.get(int(raw), "POST")
    return str(raw or "POST")


@dataclass
class SchedulerRequest:
    """What a registered scheduler handler receives when a job runs."""

    name: str
    target_type: str
    method: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    topic: str = ""
    data: bytes = b""
    target: dict[str, Any] = field(default_factory=dict)


#: A scheduler handler receives the job's :class:`SchedulerRequest` on run.
SchedulerHandler = Callable[[SchedulerRequest], Any]


@dataclass
class Job:
    """A Cloud Scheduler job (its target is stored, never really scheduled)."""

    name: str
    spec: dict[str, Any] = field(default_factory=dict)
    state: str = "ENABLED"
    last_error: str | None = None

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "name": self.name,
            "state": self.state,
            "userUpdateTime": _now(),
        }
        resource.update({k: v for k, v in self.spec.items() if k != "name"})
        resource["name"] = self.name
        return resource

    def _request(self) -> SchedulerRequest:
        http = self.spec.get("httpTarget")
        if http:
            body = http.get("body")
            return SchedulerRequest(
                name=self.name,
                target_type="http",
                method=_method_name(http.get("httpMethod")),
                url=http.get("uri", ""),
                headers=dict(http.get("headers", {})),
                body=base64.b64decode(body) if body else b"",
                target=http,
            )
        pubsub = self.spec.get("pubsubTarget")
        if pubsub:
            data = pubsub.get("data")
            return SchedulerRequest(
                name=self.name,
                target_type="pubsub",
                topic=pubsub.get("topicName", ""),
                data=base64.b64decode(data) if data else b"",
                target=pubsub,
            )
        return SchedulerRequest(name=self.name, target_type="")


class SchedulerBackend(BaseBackend):
    """In-memory Cloud Scheduler state for a single project."""

    def setup(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.handlers: dict[str, SchedulerHandler] = {}

    def register_handler(self, job_name: str, handler: SchedulerHandler) -> None:
        """Bind a callable to a job; ``run_job`` delivers its target to it."""
        self.handlers[job_name] = handler

    # -- jobs --------------------------------------------------------------

    def create_job(self, parent: str, spec: dict[str, Any]) -> Job:
        name = spec.get("name")
        if not name:
            raise exceptions.bad_request("Job name is required")
        if name in self.jobs:
            raise exceptions.already_exists(f"Job already exists: {name}")
        job = Job(name=name, spec=dict(spec))
        self.jobs[name] = job
        return job

    def get_job(self, name: str) -> Job:
        try:
            return self.jobs[name]
        except KeyError:
            raise exceptions.not_found(f"Job not found: {name}")

    def list_jobs(self, parent: str) -> list[Job]:
        prefix = f"{parent}/jobs/"
        return [self.jobs[n] for n in sorted(self.jobs) if n.startswith(prefix)]

    def delete_job(self, name: str) -> None:
        self.get_job(name)
        del self.jobs[name]

    def set_state(self, name: str, state: str) -> Job:
        job = self.get_job(name)
        job.state = state
        return job

    def update_job(self, name: str, spec: dict[str, Any]) -> Job:
        job = self.get_job(name)
        job.spec.update({k: v for k, v in spec.items() if k != "name"})
        return job

    def run_job(self, name: str) -> Job:
        job = self.get_job(name)
        handler = self.handlers.get(name)
        if handler is not None:
            try:
                handler(job._request())
            except Exception as exc:  # noqa: BLE001 - recorded, not raised to caller
                job.last_error = f"{type(exc).__name__}: {exc}"
        return job


#: Project-keyed backends, inspectable via ``get_backend("cloudscheduler")[project]``.
cloudscheduler_backends: BackendDict[SchedulerBackend] = BackendDict(
    SchedulerBackend, "cloudscheduler"
)
