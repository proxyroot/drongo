"""Google Cloud Tasks mock.

Cloud Tasks defaults to gRPC and has no emulator env var, so drongo serves it
over REST and forces the client onto its REST transport during a mock scope
(via ``patchers``). The user's default client works unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudtasks import urls
from drongo.services.cloudtasks.models import (
    CloudTasksBackend,
    TaskHandler,
    cloudtasks_backends,
)
from drongo.services.cloudtasks.responses import CloudTasksResponse

__all__ = [
    "CloudTasksBackend",
    "CloudTasksResponse",
    "cloudtasks_backends",
    "register_task_handler",
    "task_handler",
]


def _project(queue_name: str) -> str:
    parts = queue_name.split("/")
    if len(parts) < 6 or parts[0] != "projects" or parts[4] != "queues":
        raise ValueError(
            "Expected a queue resource name like "
            "'projects/<p>/locations/<l>/queues/<q>', got: " + repr(queue_name)
        )
    return parts[1]


def register_task_handler(queue_name: str, handler: TaskHandler) -> None:
    """Bind a callable to a queue; dispatched tasks are delivered to it.

    The handler receives a
    :class:`~drongo.services.cloudtasks.models.TaskRequest`. A running queue
    delivers on ``create_task``; ``run_task`` always delivers.
    """
    cloudtasks_backends[_project(queue_name)].register_handler(queue_name, handler)


def task_handler(queue_name: str) -> Callable[[TaskHandler], TaskHandler]:
    """Decorator form of :func:`register_task_handler`.

    ::

        @cloudtasks.task_handler("projects/p/locations/us-central1/queues/emails")
        def handle(request):
            assert request.method == "POST"
            send(request.body)
    """

    def decorator(handler: TaskHandler) -> TaskHandler:
        register_task_handler(queue_name, handler)
        return handler

    return decorator


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
