"""Google Cloud Run Jobs mock.

Cloud Run defaults to gRPC and has no emulator env var, so drongo serves it over
REST and forces the Jobs/Executions clients onto their REST transport during a
mock scope. The user's default clients work unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudrun import urls
from drongo.services.cloudrun.models import (
    CloudRunBackend,
    JobHandler,
    cloudrun_backends,
)
from drongo.services.cloudrun.responses import CloudRunResponse

__all__ = [
    "CloudRunBackend",
    "CloudRunResponse",
    "cloudrun_backends",
    "job_handler",
    "register_job_handler",
]


def _project(job_name: str) -> str:
    parts = job_name.split("/")
    if len(parts) < 6 or parts[0] != "projects" or parts[4] != "jobs":
        raise ValueError(
            "Expected a job resource name like "
            "'projects/<p>/locations/<l>/jobs/<id>', got: " + repr(job_name)
        )
    return parts[1]


def register_job_handler(job_name: str, handler: JobHandler) -> None:
    """Bind a Python callable to a job so ``run_job`` executes it.

    ``job_name`` is the full resource name
    (``projects/<p>/locations/<l>/jobs/<id>``). Call this inside an active
    ``mock_gcp`` scope; the binding is cleared when the scope resets.
    """
    cloudrun_backends[_project(job_name)].register_handler(job_name, handler)


def job_handler(job_name: str) -> Callable[[JobHandler], JobHandler]:
    """Decorator form of :func:`register_job_handler`.

    ::

        @cloudrun.job_handler("projects/p/locations/us-central1/jobs/nightly")
        def nightly():
            ...  # real work; runs when the client calls run_job
    """

    def decorator(handler: JobHandler) -> JobHandler:
        register_job_handler(job_name, handler)
        return handler

    return decorator


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
