"""Google Cloud Storage mock.

Registers the ``storage`` service with the gato engine on import.
"""

from __future__ import annotations

from gato.core.registry import ServiceDefinition, register_service
from gato.services.storage import urls
from gato.services.storage.models import StorageBackend, storage_backends
from gato.services.storage.responses import StorageResponse

__all__ = ["StorageBackend", "StorageResponse", "storage_backends"]

register_service(
    ServiceDefinition(
        name="storage",
        backends=storage_backends,
        response=StorageResponse(urls.url_bases, urls.url_paths),
    )
)
