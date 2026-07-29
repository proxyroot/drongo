"""HTTP handlers implementing the Cloud Tasks REST (v2) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``), so the user's normal client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core import exceptions
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.cloudtasks.models import CloudTasksBackend, cloudtasks_backends


class CloudTasksResponse(BaseResponse):
    """Handles Cloud Tasks REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> CloudTasksBackend:
        return cloudtasks_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _queue_name(self, request: Request) -> str:
        return f"{self._parent(request)}/queues/{request.path_params['queue']}"

    def _task_name(self, request: Request) -> str:
        return f"{self._queue_name(request)}/tasks/{request.path_params['task']}"

    # -- queues ------------------------------------------------------------

    def create_queue(self, request: Request) -> HttpResponse:
        body = request.json()
        name = body.get("name")
        if not name:
            raise exceptions.bad_request("Required field: queue.name")
        return json_response(self.backend_for(request).create_queue(name).to_resource())

    def get_queue(self, request: Request) -> HttpResponse:
        queue = self.backend_for(request).get_queue(self._queue_name(request))
        return json_response(queue.to_resource())

    def list_queues(self, request: Request) -> HttpResponse:
        queues = self.backend_for(request).list_queues(self._parent(request))
        return json_response({"queues": [q.to_resource() for q in queues]})

    def delete_queue(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_queue(self._queue_name(request))
        return json_response({})

    def purge_queue(self, request: Request) -> HttpResponse:
        queue = self.backend_for(request).purge_queue(self._queue_name(request))
        return json_response(queue.to_resource())

    def pause_queue(self, request: Request) -> HttpResponse:
        queue = self.backend_for(request).set_queue_state(
            self._queue_name(request), "PAUSED"
        )
        return json_response(queue.to_resource())

    def resume_queue(self, request: Request) -> HttpResponse:
        queue = self.backend_for(request).set_queue_state(
            self._queue_name(request), "RUNNING"
        )
        return json_response(queue.to_resource())

    # -- tasks -------------------------------------------------------------

    def create_task(self, request: Request) -> HttpResponse:
        task: dict[str, Any] = request.json().get("task", {})
        created = self.backend_for(request).create_task(self._queue_name(request), task)
        return json_response(created.to_resource())

    def get_task(self, request: Request) -> HttpResponse:
        task = self.backend_for(request).get_task(
            self._queue_name(request), self._task_name(request)
        )
        return json_response(task.to_resource())

    def list_tasks(self, request: Request) -> HttpResponse:
        tasks = self.backend_for(request).list_tasks(self._queue_name(request))
        return json_response({"tasks": [t.to_resource() for t in tasks]})

    def delete_task(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_task(
            self._queue_name(request), self._task_name(request)
        )
        return json_response({})

    def run_task(self, request: Request) -> HttpResponse:
        task = self.backend_for(request).run_task(
            self._queue_name(request), self._task_name(request)
        )
        return json_response(task.to_resource())
