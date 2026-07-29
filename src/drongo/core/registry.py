"""Registry of mocked services.

Each service module builds a :class:`ServiceDefinition` (a project-keyed
:class:`~drongo.core.backend.BackendDict` plus a
:class:`~drongo.core.responses.BaseResponse`) and calls :func:`register_service`
at import time. The controller walks the registry to wire every service's routes
into the interception layer and to reset state between tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from drongo.core.backend import BackendDict
from drongo.core.emulator import BaseEmulator
from drongo.core.responses import BaseResponse


@dataclass(frozen=True)
class ServiceDefinition:
    """Everything the engine needs to mock one GCP service.

    A service provides a project-keyed ``backends`` plus at least one interception
    mechanism: an HTTP ``response`` router (for REST/JSON services) and/or an
    ``emulator`` (an in-process server for gRPC-first services).
    """

    name: str
    backends: BackendDict
    response: BaseResponse | None = None
    emulator: BaseEmulator | None = None


_SERVICES: dict[str, ServiceDefinition] = {}


def register_service(definition: ServiceDefinition) -> None:
    """Register (or replace) a service. Called at service-module import time."""
    _SERVICES[definition.name] = definition


def iter_services() -> list[ServiceDefinition]:
    """Return all registered services in a stable order."""
    return [_SERVICES[name] for name in sorted(_SERVICES)]


def get_backend(name: str) -> BackendDict:
    """Return a service's project-keyed backends by name (e.g. ``"storage"``).

    Mirrors ``moto.backends.get_backend``::

        from drongo import get_backend
        get_backend("storage")["my-project"].buckets  # -> {name: Bucket}
    """
    try:
        return _SERVICES[name].backends
    except KeyError:
        known = ", ".join(sorted(_SERVICES)) or "<none>"
        raise KeyError(
            f"No mocked service named {name!r}. Registered services: {known}."
        ) from None


def reset_all_backends() -> None:
    """Reset every registered service's backends to empty state."""
    for definition in _SERVICES.values():
        definition.backends.reset()
