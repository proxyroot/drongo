"""In-memory models for Artifact Registry (``artifactregistry`` v1).

Artifact Registry defaults to gRPC but ships a REST transport and has no emulator
env var, so drongo forces the client onto REST (see ``__init__.py``) and serves
it from the HTTP layer. Every resource type - repositories, packages, versions,
tags, files - shares one name-keyed store; the collection segment of a resource
name keeps them apart.

Repositories and tags have full client CRUD. Packages, versions and files are
normally created by *pushing* artifacts (there is no create RPC for them), so
this backend exposes ``add_package`` / ``add_version`` / ``add_file`` seeding
helpers for tests to populate them, then exercise list/get/delete via the client.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["ArtifactRegistryBackend", "artifactregistry_backends"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ArtifactRegistryBackend(BaseBackend):
    """In-memory Artifact Registry state for a single project."""

    def setup(self) -> None:
        self.resources: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    # -- long-running operations ------------------------------------------

    def operation(self, parent: str, response: dict[str, Any] | None) -> dict[str, Any]:
        name = f"{parent}/operations/{self._next()}"
        op: dict[str, Any] = {"name": name, "done": True}
        if response is not None:
            op["response"] = response
        self.operations[name] = op
        return op

    def get_operation(self, name: str) -> dict[str, Any]:
        return self.operations.get(name, {"name": name, "done": True})

    # -- generic resource CRUD --------------------------------------------

    def create(
        self,
        parent: str,
        collection: str,
        resource: dict[str, Any],
        resource_id: str,
    ) -> dict[str, Any]:
        name = f"{parent}/{collection}/{resource_id}"
        if name in self.resources:
            raise exceptions.already_exists(f"Already exists: {name}")
        resource = dict(resource)
        resource["name"] = name
        resource.setdefault("createTime", _now())
        resource["updateTime"] = _now()
        self.resources[name] = resource
        return resource

    def get(self, name: str) -> dict[str, Any]:
        try:
            return self.resources[name]
        except KeyError:
            raise exceptions.not_found(f"Not found: {name}")

    def list_resources(self, parent: str, collection: str) -> list[dict[str, Any]]:
        prefix = f"{parent}/{collection}/"
        return [
            self.resources[n]
            for n in sorted(self.resources)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]

    def delete(self, name: str) -> None:
        self.get(name)
        del self.resources[name]

    def update(self, resource: dict[str, Any], paths: list[str]) -> dict[str, Any]:
        stored = self.get(resource.get("name", ""))
        fields = paths or [k for k in resource if k != "name"]
        for field in fields:
            top = field.split(".")[0]
            if top in resource:
                stored[top] = resource[top]
        stored["updateTime"] = _now()
        return stored

    # -- seeding helpers (packages/versions/files have no create RPC) ------

    def add_package(
        self, repository: str, package_id: str, **fields: Any
    ) -> dict[str, Any]:
        """Seed a package under a repository (as a push would create it)."""
        return self.create(repository, "packages", dict(fields), package_id)

    def add_version(
        self, package: str, version_id: str, **fields: Any
    ) -> dict[str, Any]:
        """Seed a version under a package."""
        return self.create(package, "versions", dict(fields), version_id)

    def add_file(self, repository: str, file_id: str, **fields: Any) -> dict[str, Any]:
        """Seed a file under a repository."""
        return self.create(repository, "files", dict(fields), file_id)


#: Project-keyed backends, inspectable via ``get_backend("artifactregistry")[p]``.
artifactregistry_backends: BackendDict[ArtifactRegistryBackend] = BackendDict(
    ArtifactRegistryBackend, "artifactregistry"
)
