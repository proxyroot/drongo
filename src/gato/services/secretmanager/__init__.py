"""Google Cloud Secret Manager mock.

Registers the ``secretmanager`` service with the gato engine on import.
"""

from __future__ import annotations

from gato.core.registry import ServiceDefinition, register_service
from gato.services.secretmanager import urls
from gato.services.secretmanager.models import (
    SecretManagerBackend,
    secretmanager_backends,
)
from gato.services.secretmanager.responses import SecretManagerResponse

__all__ = [
    "SecretManagerBackend",
    "SecretManagerResponse",
    "secretmanager_backends",
]

register_service(
    ServiceDefinition(
        name="secretmanager",
        backends=secretmanager_backends,
        response=SecretManagerResponse(urls.url_bases, urls.url_paths),
    )
)
