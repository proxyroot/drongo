"""HTTP handlers implementing the Cloud Functions REST (v2) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``).
"""

from __future__ import annotations

from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.cloudfunctions.models import (
    CloudFunctionsBackend,
    cloudfunctions_backends,
)


class CloudFunctionsResponse(BaseResponse):
    """Handles Cloud Functions REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> CloudFunctionsBackend:
        return cloudfunctions_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _function_name(self, request: Request) -> str:
        return f"{self._parent(request)}/functions/{request.path_params['function']}"

    def generate_upload_url(self, request: Request) -> HttpResponse:
        # Stub: real deploys upload source here first. Tests usually call
        # create_function directly, so return a plausible URL + storage source.
        parent = self._parent(request)
        return json_response(
            {
                "uploadUrl": f"https://storage.googleapis.com/drongo-uploads/{parent}",
                "storageSource": {
                    "bucket": "drongo-uploads",
                    "object": "source.zip",
                    "generation": "1",
                },
            }
        )

    def create_function(self, request: Request) -> HttpResponse:
        spec: dict[str, Any] = request.json()
        operation = self.backend_for(request).create_function(
            self._parent(request), request.param("functionId") or "", spec
        )
        return json_response(operation)

    def get_function(self, request: Request) -> HttpResponse:
        function = self.backend_for(request).get_function(self._function_name(request))
        return json_response(function.to_resource())

    def list_functions(self, request: Request) -> HttpResponse:
        functions = self.backend_for(request).list_functions(self._parent(request))
        return json_response({"functions": [f.to_resource() for f in functions]})

    def update_function(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).update_function(
            self._function_name(request), request.json()
        )
        return json_response(operation)

    def delete_function(self, request: Request) -> HttpResponse:
        operation = self.backend_for(request).delete_function(
            self._function_name(request)
        )
        return json_response(operation)

    def get_operation(self, request: Request) -> HttpResponse:
        p = request.path_params
        name = (
            f"projects/{p['project']}/locations/{p['location']}"
            f"/operations/{p['operation']}"
        )
        return json_response(self.backend_for(request).get_operation(name))
