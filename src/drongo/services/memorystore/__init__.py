"""Google Cloud Memorystore for Redis mock (instance admin).

Memorystore defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST during a mock scope and serves it via the HTTP interception
layer. The user's default client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.memorystore import urls
from drongo.services.memorystore.models import (
    MemorystoreBackend,
    memorystore_backends,
)
from drongo.services.memorystore.responses import MemorystoreResponse

__all__ = [
    "MemorystoreBackend",
    "MemorystoreResponse",
    "memorystore_backends",
]


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.redis_v1", "CloudRedisClient")])


register_service(
    ServiceDefinition(
        name="memorystore",
        backends=memorystore_backends,
        response=MemorystoreResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
