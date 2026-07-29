"""Google Cloud Run Jobs mock.

Cloud Run defaults to gRPC and has no emulator env var, so drongo serves it over
REST and forces the Jobs/Executions clients onto their REST transport during a
mock scope. The user's default clients work unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudrun import urls
from drongo.services.cloudrun.models import CloudRunBackend, cloudrun_backends
from drongo.services.cloudrun.responses import CloudRunResponse

__all__ = ["CloudRunBackend", "CloudRunResponse", "cloudrun_backends"]


def _patchers() -> list[Any]:
    return force_rest_patchers(
        [
            ("google.cloud.run_v2", "JobsClient"),
            ("google.cloud.run_v2", "ExecutionsClient"),
        ]
    )


register_service(
    ServiceDefinition(
        name="cloudrun",
        backends=cloudrun_backends,
        response=CloudRunResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
