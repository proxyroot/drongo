"""Google Cloud Vertex AI / AI Platform mock.

Vertex AI defaults to gRPC and has no emulator env var, so drongo serves it over
REST and forces the service clients onto their REST transport during a mock
scope. The user's default clients work unchanged.

Scoped to the control plane: datasets, endpoints, models, custom jobs, and batch
prediction jobs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.vertexai import urls
from drongo.services.vertexai.models import (
    PredictionHandler,
    VertexAIBackend,
    vertexai_backends,
)
from drongo.services.vertexai.responses import VertexAIResponse

__all__ = [
    "VertexAIBackend",
    "VertexAIResponse",
    "prediction_handler",
    "register_prediction_handler",
    "vertexai_backends",
]

_CLIENTS = [
    ("google.cloud.aiplatform_v1", "DatasetServiceClient"),
    ("google.cloud.aiplatform_v1", "EndpointServiceClient"),
    ("google.cloud.aiplatform_v1", "ModelServiceClient"),
    ("google.cloud.aiplatform_v1", "JobServiceClient"),
    ("google.cloud.aiplatform_v1", "PredictionServiceClient"),
]


def _project(endpoint_name: str) -> str:
    parts = endpoint_name.split("/")
    if len(parts) < 6 or parts[0] != "projects" or parts[4] != "endpoints":
        raise ValueError(
            "Expected an endpoint resource name like "
            "'projects/<p>/locations/<l>/endpoints/<id>', got: " + repr(endpoint_name)
        )
    return parts[1]


def register_prediction_handler(endpoint_name: str, handler: PredictionHandler) -> None:
    """Bind a callable to an endpoint so ``predict`` runs it.

    The handler receives ``(instances, parameters)`` and returns the list of
    predictions. ``endpoint_name`` is the full resource name
    (``projects/<p>/locations/<l>/endpoints/<id>``). Call this inside an active
    ``mock_gcp`` scope; the binding is cleared when the scope resets.
    """
    vertexai_backends[_project(endpoint_name)].register_prediction_handler(
        endpoint_name, handler
    )


def prediction_handler(
    endpoint_name: str,
) -> Callable[[PredictionHandler], PredictionHandler]:
    """Decorator form of :func:`register_prediction_handler`.

    ::

        @vertexai.prediction_handler("projects/p/locations/us-central1/endpoints/1")
        def predict(instances, parameters):
            return [{"score": 0.9} for _ in instances]
    """

    def decorator(handler: PredictionHandler) -> PredictionHandler:
        register_prediction_handler(endpoint_name, handler)
        return handler

    return decorator


def _patchers() -> list[Any]:
    return force_rest_patchers(_CLIENTS)


register_service(
    ServiceDefinition(
        name="vertexai",
        backends=vertexai_backends,
        response=VertexAIResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
