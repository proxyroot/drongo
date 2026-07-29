"""Google Cloud Secret Manager mock.

Registers the ``secretmanager`` service with the drongo engine on import.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.secretmanager import urls
from drongo.services.secretmanager.models import (
    SecretManagerBackend,
    secretmanager_backends,
)
from drongo.services.secretmanager.responses import SecretManagerResponse

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
