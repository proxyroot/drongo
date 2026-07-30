"""In-memory models for Cloud Functions (2nd gen).

Cloud Functions defaults to gRPC but ships a REST transport, so drongo forces the
client onto REST. Like Cloud Run, mutating calls (create/update/delete) are
long-running operations completed synchronously: each returns a *done* Operation
with the resulting Function embedded, replayed by the operations endpoint.

The function spec (build/service config, triggers) is stored opaquely; this layer
just manages resources. 2nd-gen functions are invoked via their HTTP URL, not an
Admin API call, so there is no synchronous invoke here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["CloudFunctionsBackend", "Function", "cloudfunctions_backends"]

_FUNCTION_TYPE = "type.googleapis.com/google.cloud.functions.v2.Function"
_EMPTY_TYPE = "type.googleapis.com/google.protobuf.Empty"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Function:
    """A Cloud Function (2nd gen). Its config is stored, never really deployed."""

    name: str
    spec: dict[str, Any] = field(default_factory=dict)
    create_time: str = field(default_factory=_now)

    def to_resource(self) -> dict[str, Any]:
        # projects/<p>/locations/<loc>/functions/<id>
        parts = self.name.split("/")
        project, location, fn_id = parts[1], parts[3], parts[5]
        resource: dict[str, Any] = {
            "name": self.name,
            "state": "ACTIVE",
            "createTime": self.create_time,
            "updateTime": self.create_time,
            "url": f"https://{location}-{project}.cloudfunctions.net/{fn_id}",
            "environment": "GEN_2",
        }
        resource.update({k: v for k, v in self.spec.items() if k != "name"})
        resource["name"] = self.name
        return resource


class CloudFunctionsBackend(BaseBackend):
    """In-memory Cloud Functions state for a single project."""

    def setup(self) -> None:
        self.functions: dict[str, Function] = {}
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

    # -- functions ---------------------------------------------------------

    def create_function(
        self, parent: str, function_id: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        name = f"{parent}/functions/{function_id}"
        if name in self.functions:
            raise exceptions.already_exists(f"Function already exists: {name}")
        function = Function(name=name, spec=dict(spec or {}))
        self.functions[name] = function
        return self._operation(parent, _FUNCTION_TYPE, function.to_resource())

    def get_function(self, name: str) -> Function:
        try:
            return self.functions[name]
        except KeyError:
            raise exceptions.not_found(f"Function not found: {name}")

    def list_functions(self, parent: str) -> list[Function]:
        prefix = f"{parent}/functions/"
        return [
            self.functions[n] for n in sorted(self.functions) if n.startswith(prefix)
        ]

    def update_function(self, name: str, spec: dict[str, Any]) -> dict[str, Any]:
        function = self.get_function(name)
        function.spec.update({k: v for k, v in spec.items() if k != "name"})
        location = name.rsplit("/functions/", 1)[0]
        return self._operation(location, _FUNCTION_TYPE, function.to_resource())

    def delete_function(self, name: str) -> dict[str, Any]:
        self.get_function(name)  # 404 if missing
        del self.functions[name]
        location = name.rsplit("/functions/", 1)[0]
        # DeleteFunction's LRO resolves to Empty, not a Function.
        return self._operation(location, _EMPTY_TYPE, {})


#: Project-keyed backends, inspectable via ``get_backend("cloudfunctions")[project]``.
cloudfunctions_backends: BackendDict[CloudFunctionsBackend] = BackendDict(
    CloudFunctionsBackend, "cloudfunctions"
)
