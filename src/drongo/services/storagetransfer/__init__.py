"""Google Cloud Storage Transfer Service mock.

Storage Transfer defaults to gRPC but ships a REST transport and has no emulator
env var, so drongo forces the client onto REST during a mock scope and serves it
from the HTTP layer. The user's default client works unchanged.

Covers transfer jobs (CRUD + run), transfer operations (get/list/pause/resume/
cancel), the Google-managed service account, and agent pools.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.storagetransfer import urls
from drongo.services.storagetransfer.models import (
    StorageTransferBackend,
    storagetransfer_backends,
)
from drongo.services.storagetransfer.responses import StorageTransferResponse

__all__ = [
    "StorageTransferBackend",
    "StorageTransferResponse",
    "storagetransfer_backends",
]


def _patchers() -> list[Any]:
    return force_rest_patchers(
        [("google.cloud.storage_transfer_v1", "StorageTransferServiceClient")]
    )


register_service(
    ServiceDefinition(
        name="storagetransfer",
        backends=storagetransfer_backends,
        response=StorageTransferResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
