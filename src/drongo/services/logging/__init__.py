"""Google Cloud Logging mock (log entries).

Cloud Logging's client is gRPC-only (no REST transport, no emulator env var), so
drongo runs an in-process gRPC :class:`LoggingEmulator` and its ``patchers``
inject a transport pointing the default client at it. The high-level
``logging.Client`` defaults to the gRPC path, so it works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_local_grpc_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.logging.emulator import LoggingEmulator
from drongo.services.logging.models import LoggingBackend, logging_backends

__all__ = ["LoggingBackend", "LoggingEmulator", "logging_backends"]

_emulator = LoggingEmulator(logging_backends)


def _patchers() -> list[Any]:
    return force_local_grpc_patchers(
        _emulator,
        [
            (
                "google.cloud.logging_v2.services.logging_service_v2",
                "LoggingServiceV2Client",
            )
        ],
    )


register_service(
    ServiceDefinition(
        name="logging",
        backends=logging_backends,
        emulator=_emulator,
        patchers=_patchers,
    )
)
