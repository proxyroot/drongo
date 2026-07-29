"""Google Cloud Resource Manager mock (Projects, v3).

Resource Manager defaults to gRPC and has no emulator env var, so drongo serves
it over REST and forces the ``ProjectsClient`` onto its REST transport during a
mock scope. The user's default client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.resourcemanager import urls
from drongo.services.resourcemanager.models import (
    ResourceManagerBackend,
    resourcemanager_backends,
)
from drongo.services.resourcemanager.responses import ResourceManagerResponse

__all__ = [
    "ResourceManagerBackend",
    "ResourceManagerResponse",
    "resourcemanager_backends",
]


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.resourcemanager_v3", "ProjectsClient")])


register_service(
    ServiceDefinition(
        name="resourcemanager",
        backends=resourcemanager_backends,
        response=ResourceManagerResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
