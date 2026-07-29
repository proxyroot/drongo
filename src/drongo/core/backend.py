"""Backend base class and the project-keyed ``BackendDict``.

This mirrors moto's ``moto.core.base_backend`` design, adapted to GCP:

* moto keys backends by ``account_id`` **and** ``region``; GCP's natural shard
  key is the **project**, so drongo's :class:`BackendDict` maps ``project -> backend``.
* Some GCP services have a *global* resource namespace (Cloud Storage buckets
  are globally unique, exactly like S3 in moto). Those pass
  ``global_namespace=True`` so every project shares one backend - the same
  special-case moto applies to S3.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Iterator
from typing import Generic, TypeVar


class BaseBackend(abc.ABC):
    """In-memory state for one service within one project.

    Subclasses implement :meth:`setup` to (re)initialise their state; it is
    called when the backend is created and again on every :meth:`reset`.
    """

    def __init__(self, project: str) -> None:
        self.project = project
        self.setup()

    @abc.abstractmethod
    def setup(self) -> None:
        """Initialise empty state (called on construction and on reset)."""

    def reset(self) -> None:
        """Return the backend to its initial, empty condition."""
        self.setup()


B = TypeVar("B", bound=BaseBackend)


class BackendDict(Generic[B]):
    """Lazily maps a GCP project id to that project's backend.

    Access a project's backend with ``backends["my-project"]``; it is created on
    first use. This is drongo's analogue of moto's ``BackendDict``.
    """

    def __init__(
        self,
        backend_factory: Callable[[str], B],
        service_name: str,
        *,
        global_namespace: bool = False,
    ) -> None:
        self.backend_factory = backend_factory
        self.service_name = service_name
        self.global_namespace = global_namespace
        self._backends: dict[str, B] = {}
        self._global: B | None = None

    def __getitem__(self, project: str) -> B:
        if self.global_namespace:
            if self._global is None:
                self._global = self.backend_factory(project)
            return self._global
        if project not in self._backends:
            self._backends[project] = self.backend_factory(project)
        return self._backends[project]

    def __contains__(self, project: str) -> bool:
        if self.global_namespace:
            return self._global is not None
        return project in self._backends

    def __iter__(self) -> Iterator[str]:
        return iter(self._backends)

    def reset(self) -> None:
        """Reset every project's backend to empty (used between tests)."""
        if self.global_namespace:
            if self._global is not None:
                self._global.reset()
        else:
            for backend in self._backends.values():
                backend.reset()
            self._backends.clear()
