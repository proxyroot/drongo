"""In-memory models for Cloud Logging (log entries).

Cloud Logging's client is gRPC-only, so drongo serves it from an in-process gRPC
emulator (see emulator.py) and injects a transport into the default client.
Entries are kept opaque here (the emulator owns the LogEntry proto handling);
this layer is a simple, global append log with per-project filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["LoggingBackend", "StoredEntry", "logging_backends"]


@dataclass
class StoredEntry:
    """One written log entry plus the bits needed to filter/list it."""

    seq: int
    resource_name: str  # projects/<project>
    log_name: str  # projects/<project>/logs/<id>
    entry: Any  # opaque LogEntry proto


class LoggingBackend(BaseBackend):
    """In-memory Cloud Logging state: an append-only list of entries."""

    def setup(self) -> None:
        self.entries: list[StoredEntry] = []
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def write(self, log_name: str, entry: Any) -> None:
        parts = log_name.split("/")
        project = parts[1] if len(parts) > 1 else ""
        self.entries.append(
            StoredEntry(self._next(), f"projects/{project}", log_name, entry)
        )

    def list_entries(
        self, resource_names: list[str], descending: bool
    ) -> list[StoredEntry]:
        if resource_names:
            items = [e for e in self.entries if e.resource_name in resource_names]
        else:
            items = self.entries
        return sorted(items, key=lambda e: e.seq, reverse=descending)

    def delete_log(self, log_name: str) -> None:
        self.entries = [e for e in self.entries if e.log_name != log_name]

    def list_logs(self, project: str) -> list[str]:
        prefix = f"projects/{project}"
        names = {e.log_name for e in self.entries if e.resource_name == prefix}
        return sorted(names)


#: Global-namespace backend (entries carry their project in the log name);
#: inspect via ``get_backend("logging")[anything]``.
logging_backends: BackendDict[LoggingBackend] = BackendDict(
    LoggingBackend, "logging", global_namespace=True
)
