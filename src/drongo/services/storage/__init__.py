"""Google Cloud Storage mock.

Registers the ``storage`` service with the drongo engine on import. Signed-URL
generation needs a private key to sign with, which the mock's anonymous
credentials do not have, so a patcher replaces ``generate_signed_url`` with one
that returns a deterministic URL pointing back at the mock (served via the XML
API routes in ``responses.py``).
"""

from __future__ import annotations

from typing import Any
from unittest import mock
from urllib.parse import quote

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.storage import urls
from drongo.services.storage.models import StorageBackend, storage_backends
from drongo.services.storage.responses import StorageResponse

__all__ = ["StorageBackend", "StorageResponse", "storage_backends"]

_SIGNED_MARKER = (
    "X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-SignedHeaders=host"
    "&X-Goog-Signature=drongo-mock-signature"
)


def _patchers() -> list[Any]:
    """Patch ``generate_signed_url`` so it works without signing credentials."""
    try:
        from google.cloud.storage.blob import Blob
        from google.cloud.storage.bucket import Bucket
    except ImportError:  # pragma: no cover - storage lib optional
        return []

    def blob_signed_url(self: Any, *args: Any, **kwargs: Any) -> str:
        path = f"{self.bucket.name}/{quote(self.name, safe='')}"
        return f"https://storage.googleapis.com/{path}?{_SIGNED_MARKER}"

    def bucket_signed_url(self: Any, *args: Any, **kwargs: Any) -> str:
        return f"https://storage.googleapis.com/{self.name}?{_SIGNED_MARKER}"

    return [
        mock.patch.object(Blob, "generate_signed_url", blob_signed_url),
        mock.patch.object(Bucket, "generate_signed_url", bucket_signed_url),
    ]


register_service(
    ServiceDefinition(
        name="storage",
        backends=storage_backends,
        response=StorageResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
