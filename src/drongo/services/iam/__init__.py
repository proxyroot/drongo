"""Google Cloud IAM Admin mock (service accounts and keys).

IAM Admin's client (``iam_admin_v1.IAMClient``) is gRPC-only: it ships no REST
transport and honors no emulator env var. So drongo runs an in-process gRPC
:class:`IAMEmulator` and its ``patchers`` inject a transport pointing the default
client at it (see :func:`drongo.core.patching.force_local_grpc_patchers`). The
user's normal client works unchanged.
"""

from __future__ import annotations

from typing import Any

from drongo.core.patching import force_local_grpc_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.iam.emulator import IAMEmulator
from drongo.services.iam.models import IAMBackend, iam_backends

__all__ = ["IAMBackend", "IAMEmulator", "iam_backends"]

_emulator = IAMEmulator(iam_backends)


def _patchers() -> list[Any]:
    return force_local_grpc_patchers(
        _emulator, [("google.cloud.iam_admin_v1", "IAMClient")]
    )


register_service(
    ServiceDefinition(
        name="iam",
        backends=iam_backends,
        emulator=_emulator,
        patchers=_patchers,
    )
)
