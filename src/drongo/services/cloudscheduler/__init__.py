"""Google Cloud Scheduler mock (cron jobs).

Cloud Scheduler defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST during a mock scope and serves it via the HTTP interception
layer. A mock can't tick a cron schedule, so ``run_job`` is the trigger: register
a handler with :func:`job_handler` and it runs when the client calls ``run_job``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudscheduler import urls
from drongo.services.cloudscheduler.models import (
    SchedulerBackend,
    SchedulerHandler,
    cloudscheduler_backends,
)
from drongo.services.cloudscheduler.responses import SchedulerResponse

__all__ = [
    "SchedulerBackend",
    "SchedulerResponse",
    "cloudscheduler_backends",
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


def register_job_handler(job_name: str, handler: SchedulerHandler) -> None:
    """Bind a callable to a scheduler job; ``run_job`` delivers its target to it.

    The handler receives a
    :class:`~drongo.services.cloudscheduler.models.SchedulerRequest`.
    """
    cloudscheduler_backends[_project(job_name)].register_handler(job_name, handler)


def job_handler(job_name: str) -> Callable[[SchedulerHandler], SchedulerHandler]:
    """Decorator form of :func:`register_job_handler`.

    ::

        @cloudscheduler.job_handler("projects/p/locations/us-central1/jobs/nightly")
        def run(request):
            send(request.url, request.body)   # runs on run_job
    """

    def decorator(handler: SchedulerHandler) -> SchedulerHandler:
        register_job_handler(job_name, handler)
        return handler

    return decorator


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.scheduler_v1", "CloudSchedulerClient")])


register_service(
    ServiceDefinition(
        name="cloudscheduler",
        backends=cloudscheduler_backends,
        response=SchedulerResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
