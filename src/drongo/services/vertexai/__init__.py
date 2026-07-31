"""Google Cloud Vertex AI / AI Platform mock.

Vertex AI defaults to gRPC and has no emulator env var, so drongo serves it over
REST and forces the service clients onto their REST transport during a mock
scope. The user's default clients work unchanged.

Scoped to the control plane: datasets, endpoints, models, custom jobs, and batch
prediction jobs.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.vertexai import urls
from drongo.services.vertexai.models import VertexAIBackend, vertexai_backends
from drongo.services.vertexai.responses import VertexAIResponse

__all__ = ["VertexAIBackend", "VertexAIResponse", "vertexai_backends"]

_CLIENTS = [
    ("google.cloud.aiplatform_v1", "DatasetServiceClient"),
    ("google.cloud.aiplatform_v1", "EndpointServiceClient"),
    ("google.cloud.aiplatform_v1", "ModelServiceClient"),
    ("google.cloud.aiplatform_v1", "JobServiceClient"),
]


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
