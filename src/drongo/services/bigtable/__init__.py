"""Google Cloud Bigtable mock.

Registers the ``bigtable`` service on import. Bigtable is gRPC-first, so it is
served by an in-process gRPC :class:`BigtableEmulator` (via
``BIGTABLE_EMULATOR_HOST``) that speaks both the table-admin and data APIs. The
user's normal client works with no code change.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.bigtable.emulator import BigtableEmulator
from drongo.services.bigtable.models import BigtableBackend, bigtable_backends

__all__ = ["BigtableBackend", "BigtableEmulator", "bigtable_backends"]

register_service(
    ServiceDefinition(
        name="bigtable",
        backends=bigtable_backends,
        emulator=BigtableEmulator(bigtable_backends),
    )
)
