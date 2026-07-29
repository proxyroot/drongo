"""Google Cloud Tasks mock.

Cloud Tasks defaults to gRPC and has no emulator env var, so drongo serves it
over REST and forces the client onto its REST transport during a mock scope
(via ``patchers``). The user's default client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudtasks import urls
from drongo.services.cloudtasks.models import CloudTasksBackend, cloudtasks_backends
from drongo.services.cloudtasks.responses import CloudTasksResponse

__all__ = ["CloudTasksBackend", "CloudTasksResponse", "cloudtasks_backends"]


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.tasks_v2", "CloudTasksClient")])


register_service(
    ServiceDefinition(
        name="cloudtasks",
        backends=cloudtasks_backends,
        response=CloudTasksResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
