"""In-memory models for Storage Transfer Service (``storage_transfer`` v1).

Storage Transfer defaults to gRPC but ships a REST transport and has no emulator
env var, so drongo forces the client onto REST (see ``__init__.py``) and serves
it from the HTTP layer.

The API is shaped unusually: transfer jobs are named ``transferJobs/<id>`` (the
project is a field, not part of the name), running a job returns a long-running
``transferOperations/<id>`` operation, and agent pools live under a project. Job
names are globally unique, so this backend uses one global namespace and stores
the project as a field for list filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["StorageTransferBackend", "storagetransfer_backends"]

_TRANSFER_OPERATION = "type.googleapis.com/google.storagetransfer.v1.TransferOperation"
_EMPTY = "type.googleapis.com/google.protobuf.Empty"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class StorageTransferBackend(BaseBackend):
    """In-memory Storage Transfer state (one global namespace)."""

    def setup(self) -> None:
        self.transfer_jobs: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.agent_pools: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    # -- transfer jobs -----------------------------------------------------

    def create_transfer_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job = dict(job)
        job["name"] = f"transferJobs/{self._next()}"
        job.setdefault("status", "ENABLED")
        job.setdefault("creationTime", _now())
        job["lastModificationTime"] = _now()
        self.transfer_jobs[job["name"]] = job
        return job

    def get_transfer_job(self, name: str) -> dict[str, Any]:
        try:
            return self.transfer_jobs[name]
        except KeyError:
            raise exceptions.not_found(f"Transfer job not found: {name}")

    def list_transfer_jobs(self, project_id: str | None) -> list[dict[str, Any]]:
        return [
            job
            for name in sorted(self.transfer_jobs)
            if (job := self.transfer_jobs[name]).get("status") != "DELETED"
            and (not project_id or job.get("projectId") == project_id)
        ]

    def update_transfer_job(
        self, name: str, job: dict[str, Any], paths: list[str]
    ) -> dict[str, Any]:
        stored = self.get_transfer_job(name)
        fields = paths or [k for k in job if k not in ("name", "projectId")]
        for field in fields:
            top = field.split(".")[0]
            if top in job:
                stored[top] = job[top]
        stored["lastModificationTime"] = _now()
        return stored

    def delete_transfer_job(self, name: str) -> None:
        self.get_transfer_job(name)["status"] = "DELETED"

    def run_transfer_job(self, name: str, project_id: str) -> dict[str, Any]:
        self.get_transfer_job(name)
        op_name = (
            f"transferOperations/{project_id}-{name.split('/')[-1]}-{self._next()}"
        )
        metadata = {
            "@type": _TRANSFER_OPERATION,
            "name": op_name,
            "projectId": project_id,
            "transferJobName": name,
            "status": "SUCCESS",
            "startTime": _now(),
            "endTime": _now(),
        }
        operation = {
            "name": op_name,
            "metadata": metadata,
            "done": True,
            "response": {"@type": _EMPTY},
        }
        self.operations[op_name] = operation
        return operation

    # -- transfer operations ----------------------------------------------

    def get_operation(self, name: str) -> dict[str, Any]:
        try:
            return self.operations[name]
        except KeyError:
            raise exceptions.not_found(f"Operation not found: {name}")

    def list_operations(
        self, project_id: str | None, job_names: list[str]
    ) -> list[dict[str, Any]]:
        result = []
        for name in sorted(self.operations):
            meta = self.operations[name].get("metadata", {})
            if project_id and meta.get("projectId") != project_id:
                continue
            if job_names and meta.get("transferJobName") not in job_names:
                continue
            result.append(self.operations[name])
        return result

    def set_operation_status(self, name: str, status: str) -> None:
        self.get_operation(name).setdefault("metadata", {})["status"] = status

    # -- google service account -------------------------------------------

    def google_service_account(self, project_id: str) -> dict[str, Any]:
        return {
            "accountEmail": (
                f"project-{project_id}@storage-transfer-service.iam.gserviceaccount.com"
            ),
            "subjectId": f"{project_id}-storage-transfer",
        }

    # -- agent pools -------------------------------------------------------

    def create_agent_pool(
        self, project_id: str, pool_id: str, pool: dict[str, Any]
    ) -> dict[str, Any]:
        name = f"projects/{project_id}/agentPools/{pool_id}"
        if name in self.agent_pools:
            raise exceptions.already_exists(f"Agent pool already exists: {name}")
        pool = dict(pool)
        pool["name"] = name
        pool.setdefault("state", "CREATING")
        self.agent_pools[name] = pool
        return pool

    def get_agent_pool(self, name: str) -> dict[str, Any]:
        try:
            return self.agent_pools[name]
        except KeyError:
            raise exceptions.not_found(f"Agent pool not found: {name}")

    def list_agent_pools(self, project_id: str) -> list[dict[str, Any]]:
        prefix = f"projects/{project_id}/agentPools/"
        return [
            self.agent_pools[n]
            for n in sorted(self.agent_pools)
            if n.startswith(prefix)
        ]

    def update_agent_pool(
        self, name: str, pool: dict[str, Any], paths: list[str]
    ) -> dict[str, Any]:
        stored = self.get_agent_pool(name)
        fields = paths or [k for k in pool if k != "name"]
        for field in fields:
            top = field.split(".")[0]
            if top in pool:
                stored[top] = pool[top]
        return stored

    def delete_agent_pool(self, name: str) -> None:
        if name not in self.agent_pools:
            raise exceptions.not_found(f"Agent pool not found: {name}")
        del self.agent_pools[name]


#: Global-namespace backend, inspectable via ``get_backend("storagetransfer")[p]``.
storagetransfer_backends: BackendDict[StorageTransferBackend] = BackendDict(
    StorageTransferBackend, "storagetransfer", global_namespace=True
)
