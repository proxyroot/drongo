"""HTTP handlers implementing the Artifact Registry REST (v1) API.

Artifact Registry's client is gRPC-first; drongo forces it onto REST during a
mock scope (see ``__init__.py``). Repository create/delete and package/version
delete are long-running operations, completed synchronously here. Tags are
created and returned directly.
"""

from __future__ import annotations

from drongo.core import exceptions
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.artifactregistry.models import (
    ArtifactRegistryBackend,
    artifactregistry_backends,
)

_PREFIX = "type.googleapis.com/google.devtools.artifactregistry.v1."
REPOSITORY_TYPE = _PREFIX + "Repository"
EMPTY_TYPE = "type.googleapis.com/google.protobuf.Empty"


class ArtifactRegistryResponse(BaseResponse):
    """Handles Artifact Registry REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> ArtifactRegistryBackend:
        return artifactregistry_backends[request.path_params["project"]]

    def _location(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _repository(self, request: Request) -> str:
        repo = request.path_params["repository"]
        return f"{self._location(request)}/repositories/{repo}"

    def _package(self, request: Request) -> str:
        return f"{self._repository(request)}/packages/{request.path_params['package']}"

    # -- repositories ------------------------------------------------------

    def create_repository(self, request: Request) -> HttpResponse:
        repository_id = request.param("repositoryId")
        if not repository_id:
            raise exceptions.bad_request("Required parameter: repositoryId")
        backend = self.backend_for(request)
        repository = backend.create(
            self._location(request), "repositories", request.json(), repository_id
        )
        return json_response(
            backend.operation(
                self._location(request), {"@type": REPOSITORY_TYPE, **repository}
            )
        )

    def get_repository(self, request: Request) -> HttpResponse:
        return json_response(self.backend_for(request).get(self._repository(request)))

    def list_repositories(self, request: Request) -> HttpResponse:
        repos = self.backend_for(request).list_resources(
            self._location(request), "repositories"
        )
        return json_response({"repositories": repos})

    def update_repository(self, request: Request) -> HttpResponse:
        updated = self.backend_for(request).update(
            {**request.json(), "name": self._repository(request)}, _mask(request)
        )
        return json_response(updated)

    def delete_repository(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._repository(request))
        return json_response(
            backend.operation(self._location(request), {"@type": EMPTY_TYPE})
        )

    # -- packages ----------------------------------------------------------

    def list_packages(self, request: Request) -> HttpResponse:
        packages = self.backend_for(request).list_resources(
            self._repository(request), "packages"
        )
        return json_response({"packages": packages})

    def get_package(self, request: Request) -> HttpResponse:
        return json_response(self.backend_for(request).get(self._package(request)))

    def delete_package(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._package(request))
        return json_response(
            backend.operation(self._location(request), {"@type": EMPTY_TYPE})
        )

    # -- versions ----------------------------------------------------------

    def list_versions(self, request: Request) -> HttpResponse:
        versions = self.backend_for(request).list_resources(
            self._package(request), "versions"
        )
        return json_response({"versions": versions})

    def get_version(self, request: Request) -> HttpResponse:
        return json_response(self.backend_for(request).get(self._version(request)))

    def delete_version(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._version(request))
        return json_response(
            backend.operation(self._location(request), {"@type": EMPTY_TYPE})
        )

    def _version(self, request: Request) -> str:
        return f"{self._package(request)}/versions/{request.path_params['version']}"

    # -- tags --------------------------------------------------------------

    def create_tag(self, request: Request) -> HttpResponse:
        tag_id = request.param("tagId")
        if not tag_id:
            raise exceptions.bad_request("Required parameter: tagId")
        tag = self.backend_for(request).create(
            self._package(request), "tags", request.json(), tag_id
        )
        return json_response(tag)

    def get_tag(self, request: Request) -> HttpResponse:
        return json_response(self.backend_for(request).get(self._tag(request)))

    def list_tags(self, request: Request) -> HttpResponse:
        tags = self.backend_for(request).list_resources(self._package(request), "tags")
        return json_response({"tags": tags})

    def update_tag(self, request: Request) -> HttpResponse:
        updated = self.backend_for(request).update(
            {**request.json(), "name": self._tag(request)}, _mask(request)
        )
        return json_response(updated)

    def delete_tag(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete(self._tag(request))
        return json_response({})

    def _tag(self, request: Request) -> str:
        return f"{self._package(request)}/tags/{request.path_params['tag']}"

    # -- files -------------------------------------------------------------

    def list_files(self, request: Request) -> HttpResponse:
        files = self.backend_for(request).list_resources(
            self._repository(request), "files"
        )
        return json_response({"files": files})

    def get_file(self, request: Request) -> HttpResponse:
        name = f"{self._repository(request)}/files/{request.path_params['file']}"
        return json_response(self.backend_for(request).get(name))

    # -- operations (LRO polling) ------------------------------------------

    def get_operation(self, request: Request) -> HttpResponse:
        name = (
            f"{self._location(request)}/operations/{request.path_params['operation']}"
        )
        return json_response(self.backend_for(request).get_operation(name))


def _mask(request: Request) -> list[str]:
    update_mask = request.param("updateMask")
    return [p for p in update_mask.split(",") if p] if update_mask else []
