"""Google Cloud KMS mock (key rings, crypto keys, encrypt/decrypt).

KMS defaults to gRPC but ships a REST transport, so drongo forces the client onto
REST during a mock scope and serves it via the HTTP interception layer. The
user's default client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.kms import urls
from drongo.services.kms.models import KMSBackend, kms_backends
from drongo.services.kms.responses import KMSResponse

__all__ = ["KMSBackend", "KMSResponse", "kms_backends"]


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.kms_v1", "KeyManagementServiceClient")])


register_service(
    ServiceDefinition(
        name="kms",
        backends=kms_backends,
        response=KMSResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
