"""pytest integration for gato.

Registered automatically via the ``pytest11`` entry point, so simply installing
gato makes the fixtures below available.

Example::

    def test_bucket(gato):
        from google.cloud import storage

        storage.Client(project="p").create_bucket("b")
        assert "b" in gato.backend("storage").buckets
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from gato.core.backend import BackendDict, BaseBackend
from gato.core.credentials import DEFAULT_PROJECT
from gato.core.decorator import mock_gcp
from gato.core.registry import get_backend


class GatoFixture:
    """Handle yielded by the :func:`gato` fixture for inspecting state."""

    def backends(self, name: str) -> BackendDict:
        """Return a service's project-keyed :class:`BackendDict`."""
        return get_backend(name)

    def backend(self, name: str, project: str = DEFAULT_PROJECT) -> BaseBackend:
        """Return one project's backend for a service (default project)."""
        return get_backend(name)[project]


@pytest.fixture
def gato() -> Iterator[GatoFixture]:
    """Activate gato for the duration of a test and expose its backends."""
    with mock_gcp():
        yield GatoFixture()
