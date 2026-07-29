"""HTTP handlers implementing the Secret Manager REST (v1) API.

Construct the client with the REST transport to route it through gato::

    client = secretmanager.SecretManagerServiceClient(transport="rest")
"""

from __future__ import annotations

import base64

from gato.core import exceptions
from gato.core.responses import BaseResponse, HttpResponse, Request, json_response
from gato.services.secretmanager.models import (
    SecretManagerBackend,
    secretmanager_backends,
)


class SecretManagerResponse(BaseResponse):
    """Handles Secret Manager REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> SecretManagerBackend:
        """Resolve the project-scoped backend from the request path."""
        return secretmanager_backends[request.path_params["project"]]

    # -- secrets -----------------------------------------------------------

    def create_secret(self, request: Request) -> HttpResponse:
        secret_id = request.param("secretId")
        if not secret_id:
            raise exceptions.bad_request("Required parameter: secretId")
        body = request.json()
        secret = self.backend_for(request).create_secret(
            secret_id,
            replication=body.get("replication"),
            labels=body.get("labels"),
        )
        return json_response(secret.to_resource())

    def get_secret(self, request: Request) -> HttpResponse:
        secret = self.backend_for(request).get_secret(request.path_params["secret"])
        return json_response(secret.to_resource())

    def list_secrets(self, request: Request) -> HttpResponse:
        secrets = self.backend_for(request).list_secrets()
        return json_response(
            {
                "secrets": [secret.to_resource() for secret in secrets],
                "totalSize": len(secrets),
            }
        )

    def update_secret(self, request: Request) -> HttpResponse:
        secret = self.backend_for(request).get_secret(request.path_params["secret"])
        body = request.json()
        if "labels" in body:
            secret.labels = dict(body["labels"] or {})
        return json_response(secret.to_resource())

    def delete_secret(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_secret(request.path_params["secret"])
        return json_response({})

    # -- versions ----------------------------------------------------------

    def add_version(self, request: Request) -> HttpResponse:
        payload = request.json().get("payload", {})
        data = base64.b64decode(payload.get("data", "") or "")
        version = self.backend_for(request).add_version(
            request.path_params["secret"], data
        )
        return json_response(version.to_resource())

    def get_version(self, request: Request) -> HttpResponse:
        version = self.backend_for(request).get_version(
            request.path_params["secret"], request.path_params["version"]
        )
        return json_response(version.to_resource())

    def list_versions(self, request: Request) -> HttpResponse:
        versions = self.backend_for(request).list_versions(
            request.path_params["secret"]
        )
        return json_response(
            {
                "versions": [version.to_resource() for version in versions],
                "totalSize": len(versions),
            }
        )

    def access_version(self, request: Request) -> HttpResponse:
        version = self.backend_for(request).access_version(
            request.path_params["secret"], request.path_params["version"]
        )
        encoded = base64.b64encode(version.data).decode("ascii")
        return json_response({"name": version.name, "payload": {"data": encoded}})

    def destroy_version(self, request: Request) -> HttpResponse:
        return self._set_state(request, "DESTROYED")

    def disable_version(self, request: Request) -> HttpResponse:
        return self._set_state(request, "DISABLED")

    def enable_version(self, request: Request) -> HttpResponse:
        return self._set_state(request, "ENABLED")

    def _set_state(self, request: Request, state: str) -> HttpResponse:
        version = self.backend_for(request).set_version_state(
            request.path_params["secret"], request.path_params["version"], state
        )
        return json_response(version.to_resource())
