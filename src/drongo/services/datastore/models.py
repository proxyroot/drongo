"""In-memory models for Cloud Datastore (Firestore in Datastore mode).

Datastore is gRPC-first and the high-level client connects insecurely when
``DATASTORE_EMULATOR_HOST`` is set, so drongo serves it from an in-process gRPC
emulator (see emulator.py). Entities are stored by a canonical key string; the
emulator, which owns the Datastore proto types, computes those keys and does all
value encoding and query interpretation, keeping this layer proto-free.
"""

from __future__ import annotations

from typing import Any

from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["DatastoreBackend", "datastore_backends"]


class DatastoreBackend(BaseBackend):
    """In-memory Datastore state for a single project: entities by canonical key."""

    def setup(self) -> None:
        self.entities: dict[str, Any] = {}  # canonical key -> Entity proto
        self.versions: dict[str, int] = {}
        self._id_seq = 2000000000000000
        self._txn_seq = 0

    def next_id(self) -> int:
        self._id_seq += 1
        return self._id_seq

    def next_transaction(self) -> int:
        self._txn_seq += 1
        return self._txn_seq

    def put(self, canonical: str, entity: Any) -> int:
        self.entities[canonical] = entity
        self.versions[canonical] = self.versions.get(canonical, 0) + 1
        return self.versions[canonical]

    def get(self, canonical: str) -> Any:
        return self.entities.get(canonical)

    def exists(self, canonical: str) -> bool:
        return canonical in self.entities

    def delete(self, canonical: str) -> None:
        self.entities.pop(canonical, None)
        self.versions.pop(canonical, None)

    def all(self) -> list[Any]:
        return list(self.entities.values())


#: Project-keyed backends, inspectable via ``get_backend("datastore")[project]``.
datastore_backends: BackendDict[DatastoreBackend] = BackendDict(
    DatastoreBackend, "datastore"
)
