"""In-memory models for Cloud Firestore (Native mode).

Firestore is gRPC-first, so drongo serves it from an in-process gRPC emulator
(see :mod:`drongo.services.firestore.emulator`). Documents are stored by their
full resource name (``projects/P/databases/D/documents/col/doc[/sub/doc...]``).

Field values are kept **opaque** here: the emulator, which owns the Firestore
proto types, does all value encoding and query interpretation, so this layer
stays proto-free and is just a path-keyed document store, moto-style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["FirestoreBackend", "StoredDocument", "firestore_backends"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoredDocument:
    """A stored document: its full name, opaque field map, and timestamps."""

    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    create_time: datetime = field(default_factory=_now)
    update_time: datetime = field(default_factory=_now)


class FirestoreBackend(BaseBackend):
    """In-memory Firestore state: documents keyed by full resource name."""

    def setup(self) -> None:
        self.documents: dict[str, StoredDocument] = {}

    def get(self, name: str) -> StoredDocument | None:
        return self.documents.get(name)

    def exists(self, name: str) -> bool:
        return name in self.documents

    def put(self, name: str, fields: dict[str, Any]) -> StoredDocument:
        """Create or fully replace a document's fields."""
        existing = self.documents.get(name)
        create_time = existing.create_time if existing else _now()
        entry = StoredDocument(
            name=name,
            fields=dict(fields),
            create_time=create_time,
            update_time=_now(),
        )
        self.documents[name] = entry
        return entry

    def merge(
        self, name: str, fields: dict[str, Any], paths: list[str]
    ) -> StoredDocument:
        """Merge only ``paths`` (from a set(merge=True) / update) into a document.

        A masked path that is absent from ``fields`` deletes that field. Nested
        field paths (``a.b``) are applied at the top-level segment (``a``).
        """
        entry = self.documents.get(name)
        if entry is None:
            entry = StoredDocument(name=name)
            self.documents[name] = entry
        for path in paths:
            top = path.split(".", 1)[0]
            if top in fields:
                entry.fields[top] = fields[top]
            else:
                entry.fields.pop(top, None)
        entry.update_time = _now()
        return entry

    def delete(self, name: str) -> None:
        self.documents.pop(name, None)

    def list_collection(self, collection_path: str) -> list[StoredDocument]:
        """Return the documents whose immediate parent is ``collection_path``."""
        prefix = f"{collection_path}/"
        out = [
            entry
            for name, entry in self.documents.items()
            if name.startswith(prefix) and "/" not in name[len(prefix) :]
        ]
        return sorted(out, key=lambda e: e.name)


#: Global-namespace backend (document names already carry the project/database);
#: inspect via ``get_backend("firestore")[anything]``.
firestore_backends: BackendDict[FirestoreBackend] = BackendDict(
    FirestoreBackend, "firestore", global_namespace=True
)
