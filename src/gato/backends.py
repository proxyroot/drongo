"""Public accessor for mocked service backends (moto-style ``get_backend``).

Example::

    from gato import mock_gcp
    from gato.backends import get_backend

    with mock_gcp():
        storage.Client(project="p").create_bucket("b")
        assert "b" in get_backend("storage")["p"].buckets
"""

from __future__ import annotations

from gato.core.registry import get_backend

__all__ = ["get_backend"]
