"""Google Cloud Firestore mock (Native mode).

Registers the ``firestore`` service with the drongo engine on import. Firestore
is gRPC-first, so it is served by an in-process gRPC :class:`FirestoreEmulator`
(via ``FIRESTORE_EMULATOR_HOST``) rather than the HTTP interception layer. The
user's normal client works with no code change.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.firestore.emulator import FirestoreEmulator
from drongo.services.firestore.models import (
    FirestoreBackend,
    StoredDocument,
    firestore_backends,
)

__all__ = [
    "FirestoreBackend",
    "FirestoreEmulator",
    "StoredDocument",
    "firestore_backends",
]

register_service(
    ServiceDefinition(
        name="firestore",
        backends=firestore_backends,
        emulator=FirestoreEmulator(firestore_backends),
    )
)
