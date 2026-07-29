"""Service implementations.

Importing this package imports every service subpackage, and each one registers
itself with :mod:`gato.core.registry` as a side effect. Add a new service by
creating a subpackage here and importing it below.
"""

from __future__ import annotations

from gato.services import secretmanager, storage

__all__ = ["secretmanager", "storage"]
