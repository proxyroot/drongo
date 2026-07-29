"""In-memory models for Cloud Run Jobs (Admin API v2).

Cloud Run mutations are long-running operations (LROs): create/delete/run return
an `Operation` the client polls until done. drongo completes them synchronously:
each mutation records a *done* operation (with the resulting resource embedded)
that the operations endpoint replays for the client's poll.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

_JOB_TYPE = "type.googleapis.com/google.cloud.run.v2.Job"
_EXECUTION_TYPE = "type.googleapis.com/google.cloud.run.v2.Execution"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Execution:
    """One run of a job."""

    name: str
    job: str
    create_time: str = field(default_factory=_now)

    def to_resource(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "uid": self.name.rsplit("/", 1)[-1],
            "job": self.job.rsplit("/", 1)[-1],
            "createTime": self.create_time,
            "completionTime": self.create_time,
            "taskCount": 1,
            "succeededCount": 1,
        }


@dataclass
class Job:
    """A Cloud Run job (its container template is stored, never executed)."""

    name: str
    spec: dict[str, Any] = field(default_factory=dict)
    create_time: str = field(default_factory=_now)
    executions: dict[str, Execution] = field(default_factory=dict)

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "name": self.name,
            "uid": self.name.rsplit("/", 1)[-1],
            "createTime": self.create_time,
            "updateTime": self.create_time,
            "launchStage": "GA",
            "executionCount": len(self.executions),
        }
        resource.update(self.spec)
        resource["name"] = self.name  # spec may carry a name; ours wins
        return resource


class CloudRunBackend(BaseBackend):
    """In-memory Cloud Run Jobs state for a single project."""

    def setup(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _operation(self, parent: str, type_url: str, resource: dict) -> dict:
        name = f"{parent}/operations/op-{self._next()}"
        operation = {
            "name": name,
            "done": True,
            "response": {"@type": type_url, **resource},
        }
        self.operations[name] = operation
        return operation

    def get_operation(self, name: str) -> dict:
        # Operations complete immediately; unknown ones are reported done+empty.
        return self.operations.get(name, {"name": name, "done": True})

    # -- jobs --------------------------------------------------------------

    def create_job(self, parent: str, job_id: str, spec: dict) -> dict:
        name = f"{parent}/jobs/{job_id}"
        if name in self.jobs:
            raise exceptions.already_exists(f"Job already exists: {name}")
        job = Job(name=name, spec=dict(spec or {}))
        self.jobs[name] = job
        return self._operation(parent, _JOB_TYPE, job.to_resource())

    def get_job(self, name: str) -> Job:
        try:
            return self.jobs[name]
        except KeyError:
            raise exceptions.not_found(f"Job not found: {name}")

    def list_jobs(self, parent: str) -> list[Job]:
        prefix = f"{parent}/jobs/"
        return [self.jobs[n] for n in sorted(self.jobs) if n.startswith(prefix)]

    def delete_job(self, name: str) -> dict:
        job = self.get_job(name)
        del self.jobs[name]
        parent = name.rsplit("/jobs/", 1)[0]
        return self._operation(parent, _JOB_TYPE, job.to_resource())

    def run_job(self, name: str) -> dict:
        job = self.get_job(name)
        execution_name = f"{name}/executions/exec-{self._next()}"
        execution = Execution(name=execution_name, job=name)
        job.executions[execution_name] = execution
        parent = name.rsplit("/jobs/", 1)[0]
        return self._operation(parent, _EXECUTION_TYPE, execution.to_resource())

    # -- executions --------------------------------------------------------

    def get_execution(self, name: str) -> Execution:
        job_name = name.rsplit("/executions/", 1)[0]
        job = self.get_job(job_name)
        try:
            return job.executions[name]
        except KeyError:
            raise exceptions.not_found(f"Execution not found: {name}")

    def list_executions(self, job_name: str) -> list[Execution]:
        job = self.get_job(job_name)
        return [job.executions[n] for n in sorted(job.executions)]

    def delete_execution(self, name: str) -> dict:
        execution = self.get_execution(name)
        job_name = name.rsplit("/executions/", 1)[0]
        del self.jobs[job_name].executions[name]
        parent = job_name.rsplit("/jobs/", 1)[0]
        return self._operation(parent, _EXECUTION_TYPE, execution.to_resource())


#: Project-keyed backends, inspectable via ``get_backend("cloudrun")[project]``.
cloudrun_backends: BackendDict[CloudRunBackend] = BackendDict(
    CloudRunBackend, "cloudrun"
)
