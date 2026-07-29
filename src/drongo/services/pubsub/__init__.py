"""Google Cloud Pub/Sub mock.

Registers the ``pubsub`` service with the drongo engine on import. Pub/Sub is
gRPC-first, so it is served by an in-process gRPC :class:`PubSubEmulator` (via
``PUBSUB_EMULATOR_HOST``) rather than the HTTP interception layer.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.pubsub.emulator import PubSubEmulator
from drongo.services.pubsub.models import PubSubBackend, pubsub_backends

__all__ = ["PubSubBackend", "PubSubEmulator", "pubsub_backends"]

register_service(
    ServiceDefinition(
        name="pubsub",
        backends=pubsub_backends,
        emulator=PubSubEmulator(pubsub_backends),
    )
)
