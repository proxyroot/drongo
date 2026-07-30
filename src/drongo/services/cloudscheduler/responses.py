"""HTTP handlers implementing the Cloud Scheduler REST (v1) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``).
"""

from __future__ import annotations

from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.cloudscheduler.models import (
    SchedulerBackend,
    cloudscheduler_backends,
)


class SchedulerResponse(BaseResponse):
    """Handles Cloud Scheduler REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> SchedulerBackend:
        return cloudscheduler_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _job_name(self, request: Request) -> str:
        return f"{self._parent(request)}/jobs/{request.path_params['job']}"

    def create_job(self, request: Request) -> HttpResponse:
        job: dict[str, Any] = request.json()
        created = self.backend_for(request).create_job(self._parent(request), job)
        return json_response(created.to_resource())

    def get_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).get_job(self._job_name(request))
        return json_response(job.to_resource())

    def list_jobs(self, request: Request) -> HttpResponse:
        jobs = self.backend_for(request).list_jobs(self._parent(request))
        return json_response({"jobs": [j.to_resource() for j in jobs]})

    def delete_job(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_job(self._job_name(request))
        return json_response({})

    def update_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).update_job(
            self._job_name(request), request.json()
        )
        return json_response(job.to_resource())

    def pause_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).set_state(self._job_name(request), "PAUSED")
        return json_response(job.to_resource())

    def resume_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).set_state(self._job_name(request), "ENABLED")
        return json_response(job.to_resource())

    def run_job(self, request: Request) -> HttpResponse:
        job = self.backend_for(request).run_job(self._job_name(request))
        return json_response(job.to_resource())
