"""HTTP handlers implementing the Memorystore for Redis REST (v1) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``).
"""

from __future__ import annotations

from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.memorystore.models import (
    MemorystoreBackend,
    memorystore_backends,
)


class MemorystoreResponse(BaseResponse):
    """Handles Memorystore REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> MemorystoreBackend:
        return memorystore_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _instance_name(self, request: Request) -> str:
        return f"{self._parent(request)}/instances/{request.path_params['instance']}"

    def create_instance(self, request: Request) -> HttpResponse:
        spec: dict[str, Any] = request.json()
        operation = self.backend_for(request).create_instance(
            self._parent(request), request.param("instanceId") or "", spec
        )
        return json_response(operation)

    def get_instance(self, request: Request) -> HttpResponse:
        instance = self.backend_for(request).get_instance(self._instance_name(request))
        return json_response(instance.to_resource())

    def list_instances(self, request: Request) -> HttpResponse:
        instances = self.backend_for(request).list_instances(self._parent(request))
        return json_response({"instances": [i.to_resource() for i in instances]})

    def update_instance(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).update_instance(
            self._instance_name(request), request.json()
        )
        return json_response(operation)

    def delete_instance(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).delete_instance(
            self._instance_name(request)
        )
        return json_response(operation)

    def get_operation(self, request: Request) -> HttpResponse:
        p = request.path_params
        name = (
            f"projects/{p['project']}/locations/{p['location']}"
            f"/operations/{p['operation']}"
        )
        return json_response(self.backend_for(request).get_operation(name))
