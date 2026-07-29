"""Service implementations.

Importing this package imports every service subpackage, and each one registers
itself with :mod:`drongo.core.registry` as a side effect. Add a new service by
creating a subpackage here and importing it below.
"""

from __future__ import annotations

from drongo.services import pubsub, secretmanager, storage

__all__ = ["pubsub", "secretmanager", "storage"]
