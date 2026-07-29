"""Google Cloud Secret Manager mock.

Registers the ``secretmanager`` service with the drongo engine on import.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
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


def _patchers() -> list[Any]:
    # Secret Manager is gRPC-first with no emulator env var; force the default
    # client onto REST so the HTTP layer serves it with no code change.
    return force_rest_patchers(
        [("google.cloud.secretmanager_v1", "SecretManagerServiceClient")]
    )


register_service(
    ServiceDefinition(
        name="secretmanager",
        backends=secretmanager_backends,
        response=SecretManagerResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
