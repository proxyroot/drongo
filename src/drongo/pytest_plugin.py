"""pytest integration for drongo.

Registered automatically via the ``pytest11`` entry point, so simply installing
drongo makes the fixtures below available.

Example::

    def test_bucket(drongo):
        from google.cloud import storage

        storage.Client(project="p").create_bucket("b")
        assert "b" in drongo.backend("storage").buckets
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from drongo.core.backend import BackendDict, BaseBackend
from drongo.core.credentials import DEFAULT_PROJECT
from drongo.core.decorator import mock_gcp
from drongo.core.registry import get_backend


class DrongoFixture:
    """Handle yielded by the :func:`drongo` fixture for inspecting state."""

    def backends(self, name: str) -> BackendDict:
        """Return a service's project-keyed :class:`BackendDict`."""
        return get_backend(name)

    def backend(self, name: str, project: str = DEFAULT_PROJECT) -> BaseBackend:
        """Return one project's backend for a service (default project)."""
        return get_backend(name)[project]


@pytest.fixture
def drongo() -> Iterator[DrongoFixture]:
    """Activate drongo for the duration of a test and expose its backends."""
    with mock_gcp():
        yield DrongoFixture()
