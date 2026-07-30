"""Google Cloud Functions mock (2nd gen, admin API).

Cloud Functions defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST during a mock scope and serves it via the HTTP interception
layer. The user's default client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.cloudfunctions import urls
from drongo.services.cloudfunctions.models import (
    CloudFunctionsBackend,
    cloudfunctions_backends,
)
from drongo.services.cloudfunctions.responses import CloudFunctionsResponse

__all__ = [
    "CloudFunctionsBackend",
    "CloudFunctionsResponse",
    "cloudfunctions_backends",
]


def _patchers() -> list[Any]:
    return force_rest_patchers([("google.cloud.functions_v2", "FunctionServiceClient")])


register_service(
    ServiceDefinition(
        name="cloudfunctions",
        backends=cloudfunctions_backends,
        response=CloudFunctionsResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
