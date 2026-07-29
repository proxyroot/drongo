"""HTTP handlers implementing the Cloud Resource Manager REST (v3) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``), so the user's normal ``ProjectsClient`` works
unchanged.
"""

from __future__ import annotations

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.resourcemanager.models import (
    ResourceManagerBackend,
    resourcemanager_backends,
)

#: Projects are a single global namespace, so every lookup shares one backend.
_GLOBAL = "_global_"


class ResourceManagerResponse(BaseResponse):
    """Handles Resource Manager REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> ResourceManagerBackend:
        return resourcemanager_backends[_GLOBAL]

    def create_project(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).create_project(request.json())
        return json_response(operation)

    def get_project(self, request: Request) -> HttpResponse:
        project = self.backend_for(request).get_project(request.path_params["project"])
        return json_response(project.to_resource())

    def list_projects(self, request: Request) -> HttpResponse:
        projects = self.backend_for(request).list_projects(request.param("parent"))
        return json_response({"projects": [p.to_resource() for p in projects]})

    def search_projects(self, request: Request) -> HttpResponse:
        projects = self.backend_for(request).search_projects()
        return json_response({"projects": [p.to_resource() for p in projects]})

    def delete_project(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).delete_project(
            request.path_params["project"]
        )
        return json_response(operation)

    def undelete_project(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).undelete_project(
            request.path_params["project"]
        )
        return json_response(operation)

    def update_project(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).update_project(
            request.path_params["project"], request.json()
        )
        return json_response(operation)

    def get_operation(self, request: Request) -> HttpResponse:
        name = f"operations/{request.path_params['operation']}"
        return json_response(self.backend_for(request).get_operation(name))
