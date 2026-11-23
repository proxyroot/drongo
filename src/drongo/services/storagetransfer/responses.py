"""HTTP handlers implementing the Storage Transfer REST (v1) API.

Storage Transfer's client is gRPC-first; drongo forces it onto REST during a mock
scope (see ``__init__.py``). Running a transfer job returns a long-running
``transferOperation`` (completed synchronously here); pause/resume/cancel flip its
status. Delete marks the job ``DELETED`` (Storage Transfer never removes jobs).
"""

from __future__ import annotations

import json

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.storagetransfer.models import (
    StorageTransferBackend,
    storagetransfer_backends,
)


class StorageTransferResponse(BaseResponse):
    """Handles Storage Transfer REST requests against the in-memory backend."""

    def backend(self) -> StorageTransferBackend:
        return storagetransfer_backends["_"]

    # -- google service account -------------------------------------------

    def get_google_service_account(self, request: Request) -> HttpResponse:
        project_id = request.path_params["project"]
        return json_response(self.backend().google_service_account(project_id))

    # -- transfer jobs -----------------------------------------------------

    def create_transfer_job(self, request: Request) -> HttpResponse:
        return json_response(self.backend().create_transfer_job(request.json()))

    def get_transfer_job(self, request: Request) -> HttpResponse:
        name = f"transferJobs/{request.path_params['job']}"
        return json_response(self.backend().get_transfer_job(name))

    def list_transfer_jobs(self, request: Request) -> HttpResponse:
        project_id, _ = _filter(request)
        jobs = self.backend().list_transfer_jobs(project_id)
        return json_response({"transferJobs": jobs})

    def update_transfer_job(self, request: Request) -> HttpResponse:
        name = f"transferJobs/{request.path_params['job']}"
        body = request.json()
        mask = body.get("updateTransferJobFieldMask", "")
        paths = [p for p in mask.split(",") if p] if mask else []
        updated = self.backend().update_transfer_job(
            name, body.get("transferJob", {}), paths
        )
        return json_response(updated)

    def delete_transfer_job(self, request: Request) -> HttpResponse:
        name = f"transferJobs/{request.path_params['job']}"
        self.backend().delete_transfer_job(name)
        return json_response({})

    def run_transfer_job(self, request: Request) -> HttpResponse:
        name = f"transferJobs/{request.path_params['job']}"
        project_id = request.json().get("projectId", "")
        return json_response(self.backend().run_transfer_job(name, project_id))

    # -- transfer operations ----------------------------------------------

    def get_transfer_operation(self, request: Request) -> HttpResponse:
        name = f"transferOperations/{request.path_params['operation']}"
        return json_response(self.backend().get_operation(name))

    def list_transfer_operations(self, request: Request) -> HttpResponse:
        project_id, job_names = _filter(request)
        operations = self.backend().list_operations(project_id, job_names)
        return json_response({"operations": operations})

    def pause_transfer_operation(self, request: Request) -> HttpResponse:
        return self._set_status(request, "PAUSED")

    def resume_transfer_operation(self, request: Request) -> HttpResponse:
        return self._set_status(request, "IN_PROGRESS")

    def cancel_transfer_operation(self, request: Request) -> HttpResponse:
        return self._set_status(request, "ABORTED")

    def _set_status(self, request: Request, status: str) -> HttpResponse:
        name = f"transferOperations/{request.path_params['operation']}"
        self.backend().set_operation_status(name, status)
        return json_response({})

    # -- agent pools -------------------------------------------------------

    def create_agent_pool(self, request: Request) -> HttpResponse:
        pool_id = request.param("agentPoolId") or ""
        pool = self.backend().create_agent_pool(
            request.path_params["project"], pool_id, request.json()
        )
        return json_response(pool)

    def get_agent_pool(self, request: Request) -> HttpResponse:
        return json_response(self.backend().get_agent_pool(self._pool(request)))

    def list_agent_pools(self, request: Request) -> HttpResponse:
        pools = self.backend().list_agent_pools(request.path_params["project"])
        return json_response({"agentPools": pools})

    def update_agent_pool(self, request: Request) -> HttpResponse:
        mask = request.param("updateMask")
        paths = [p for p in mask.split(",") if p] if mask else []
        updated = self.backend().update_agent_pool(
            self._pool(request), request.json(), paths
        )
        return json_response(updated)

    def delete_agent_pool(self, request: Request) -> HttpResponse:
        self.backend().delete_agent_pool(self._pool(request))
        return json_response({})

    def _pool(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/agentPools/{p['pool']}"


def _filter(request: Request) -> tuple[str | None, list[str]]:
    """Storage Transfer passes list filters as a JSON string query parameter."""
    raw = request.param("filter")
    if not raw:
        return None, []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None, []
    return parsed.get("projectId"), parsed.get("jobNames", [])
