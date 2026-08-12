"""Google Cloud Artifact Registry mock.

Artifact Registry defaults to gRPC but ships a REST transport and has no emulator
env var, so drongo forces the client onto REST during a mock scope and serves it
from the HTTP layer. The user's default client works unchanged.

Covers repositories (CRUD), tags (CRUD), and read/delete of packages, versions
and files. Packages/versions/files have no create RPC (they come from pushed
artifacts), so seed them with the backend's ``add_package`` / ``add_version`` /
``add_file`` helpers via ``get_backend("artifactregistry")[project]``.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.artifactregistry import urls
from drongo.services.artifactregistry.models import (
    ArtifactRegistryBackend,
    artifactregistry_backends,
)
from drongo.services.artifactregistry.responses import ArtifactRegistryResponse

__all__ = [
    "ArtifactRegistryBackend",
    "ArtifactRegistryResponse",
    "artifactregistry_backends",
]


def _patchers() -> list[Any]:
    return force_rest_patchers(
        [("google.cloud.artifactregistry_v1", "ArtifactRegistryClient")]
    )


register_service(
    ServiceDefinition(
        name="artifactregistry",
        backends=artifactregistry_backends,
        response=ArtifactRegistryResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
