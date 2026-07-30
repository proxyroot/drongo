"""Google Cloud Datastore mock.

Registers the ``datastore`` service on import. Datastore is gRPC-first, so it is
served by an in-process gRPC :class:`DatastoreEmulator` (via
``DATASTORE_EMULATOR_HOST``) rather than the HTTP interception layer. The user's
normal client works with no code change.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.datastore.emulator import DatastoreEmulator
from drongo.services.datastore.models import DatastoreBackend, datastore_backends

__all__ = ["DatastoreBackend", "DatastoreEmulator", "datastore_backends"]

register_service(
    ServiceDefinition(
        name="datastore",
        backends=datastore_backends,
        emulator=DatastoreEmulator(datastore_backends),
    )
)
