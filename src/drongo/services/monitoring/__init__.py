"""Google Cloud Monitoring mock (metrics + alerting).

Cloud Monitoring's clients (``monitoring_v3.MetricServiceClient`` and friends)
are gRPC-only: they ship no REST transport and honor no emulator env var. So
drongo runs an in-process gRPC :class:`MonitoringEmulator` and its ``patchers``
inject a transport pointing the default clients at it (see
:func:`drongo.core.patching.force_local_grpc_patchers`). The user's normal
clients work unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_local_grpc_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.monitoring.emulator import MonitoringEmulator
from drongo.services.monitoring.models import MonitoringBackend, monitoring_backends

__all__ = ["MonitoringBackend", "MonitoringEmulator", "monitoring_backends"]

_emulator = MonitoringEmulator(monitoring_backends)


def _patchers() -> list[Any]:
    return force_local_grpc_patchers(
        _emulator,
        [
            ("google.cloud.monitoring_v3", "MetricServiceClient"),
            ("google.cloud.monitoring_v3", "AlertPolicyServiceClient"),
            ("google.cloud.monitoring_v3", "NotificationChannelServiceClient"),
        ],
    )


register_service(
    ServiceDefinition(
        name="monitoring",
        backends=monitoring_backends,
        emulator=_emulator,
        patchers=_patchers,
    )
)
