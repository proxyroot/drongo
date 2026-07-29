"""HTTP handlers implementing the Cloud Run Jobs REST (v2) API.

Cloud Run's client is gRPC-first; drongo forces it onto REST during a mock scope
(see ``__init__.py``). Mutations are long-running operations, completed
synchronously here (each returns a done ``Operation`` with the resource embedded).
"""

from __future__ import annotations

from drongo.core import exceptions
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.cloudrun.models import CloudRunBackend, cloudrun_backends


class CloudRunResponse(BaseResponse):
    """Handles Cloud Run Jobs REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> CloudRunBackend:
        return cloudrun_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _job_name(self, request: Request) -> str:
        return f"{self._parent(request)}/jobs/{request.path_params['job']}"

    def _execution_name(self, request: Request) -> str:
        return (
            f"{self._job_name(request)}/executions/{request.path_params['execution']}"
        )

    # -- jobs --------------------------------------------------------------

    def create_job(self, request: Request) -> HttpResponse:
        job_id = request.param("jobId")
        if not job_id:
            raise exceptions.bad_request("Required parameter: jobId")
        operation = self.backend_for(request).create_job(
            self._parent(request), job_id, request.json()
        )
        return json_response(operation)

    def get_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).get_job(self._job_name(request))
        return json_response(job.to_resource())

    def list_jobs(self, request: Request) -> HttpResponse:
        jobs = self.backend_for(request).list_jobs(self._parent(request))
        return json_response({"jobs": [job.to_resource() for job in jobs]})

    def delete_job(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).delete_job(self._job_name(request))
        return json_response(operation)

    def run_job(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).run_job(self._job_name(request))
        return json_response(operation)

    # -- executions --------------------------------------------------------

    def get_execution(self, request: Request) -> HttpResponse:
        execution = self.backend_for(request).get_execution(
            self._execution_name(request)
        )
        return json_response(execution.to_resource())

    def list_executions(self, request: Request) -> HttpResponse:
        executions = self.backend_for(request).list_executions(self._job_name(request))
        return json_response(
            {"executions": [execution.to_resource() for execution in executions]}
        )

    def delete_execution(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).delete_execution(
            self._execution_name(request)
        )
        return json_response(operation)

    # -- operations (LRO polling) ------------------------------------------

    def get_operation(self, request: Request) -> HttpResponse:
        name = f"{self._parent(request)}/operations/{request.path_params['operation']}"
        return json_response(self.backend_for(request).get_operation(name))
