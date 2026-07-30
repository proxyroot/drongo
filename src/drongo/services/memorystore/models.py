"""In-memory models for Memorystore for Redis.

Memorystore defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST. Instance mutations (create/update/delete) are long-running
operations completed synchronously: each returns a *done* Operation with the
resulting Instance embedded, replayed by the operations endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["Instance", "MemorystoreBackend", "memorystore_backends"]

_INSTANCE_TYPE = "type.googleapis.com/google.cloud.redis.v1.Instance"
_EMPTY_TYPE = "type.googleapis.com/google.protobuf.Empty"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Instance:
    """A Memorystore Redis instance."""

    name: str
    spec: dict[str, Any] = field(default_factory=dict)
    create_time: str = field(default_factory=_now)

    def to_resource(self) -> dict[str, Any]:
        parts = self.name.split("/")
        location = parts[3]
        resource: dict[str, Any] = {
            "name": self.name,
            "state": "READY",
            "host": "10.0.0.3",
            "port": 6379,
            "redisVersion": "REDIS_7_0",
            "tier": "BASIC",
            "memorySizeGb": 1,
            "currentLocationId": location,
            "createTime": self.create_time,
        }
        resource.update({k: v for k, v in self.spec.items() if k != "name"})
        resource["name"] = self.name
        return resource


class MemorystoreBackend(BaseBackend):
    """In-memory Memorystore state for a single project."""

    def setup(self) -> None:
        self.instances: dict[str, Instance] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _operation(
        self, location: str, type_url: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        name = f"{location}/operations/op-{self._next()}"
        operation = {
            "name": name,
            "done": True,
            "response": {"@type": type_url, **resource},
        }
        self.operations[name] = operation
        return operation

    def get_operation(self, name: str) -> dict[str, Any]:
        return self.operations.get(name, {"name": name, "done": True})

    # -- instances ---------------------------------------------------------

    def create_instance(
        self, parent: str, instance_id: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        name = f"{parent}/instances/{instance_id}"
        if name in self.instances:
            raise exceptions.already_exists(f"Instance already exists: {name}")
        instance = Instance(name=name, spec=dict(spec or {}))
        self.instances[name] = instance
        return self._operation(parent, _INSTANCE_TYPE, instance.to_resource())

    def get_instance(self, name: str) -> Instance:
        try:
            return self.instances[name]
        except KeyError:
            raise exceptions.not_found(f"Instance not found: {name}")

    def list_instances(self, parent: str) -> list[Instance]:
        prefix = f"{parent}/instances/"
        return [
            self.instances[n] for n in sorted(self.instances) if n.startswith(prefix)
        ]

    def update_instance(self, name: str, spec: dict[str, Any]) -> dict[str, Any]:
        instance = self.get_instance(name)
        instance.spec.update({k: v for k, v in spec.items() if k != "name"})
        location = name.rsplit("/instances/", 1)[0]
        return self._operation(location, _INSTANCE_TYPE, instance.to_resource())

    def delete_instance(self, name: str) -> dict[str, Any]:
        self.get_instance(name)  # 404 if missing
        del self.instances[name]
        location = name.rsplit("/instances/", 1)[0]
        return self._operation(location, _EMPTY_TYPE, {})


#: Project-keyed backends, inspectable via ``get_backend("memorystore")[project]``.
memorystore_backends: BackendDict[MemorystoreBackend] = BackendDict(
    MemorystoreBackend, "memorystore"
)
