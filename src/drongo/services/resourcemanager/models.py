"""In-memory models for Cloud Resource Manager (Projects, v3).

Scoped to the Projects API, the most-used part of Resource Manager. Like Cloud
Run, the mutating calls (create/delete/update/undelete) are long-running
operations completed synchronously: each returns a *done* ``Operation`` with the
resulting ``Project`` embedded, replayed by the operations endpoint.

Projects live in one global namespace (there is no enclosing project to shard
by), so a single backend holds them all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["Project", "ResourceManagerBackend", "resourcemanager_backends"]

_PROJECT_TYPE = "type.googleapis.com/google.cloud.resourcemanager.v3.Project"

#: Project numbers are system-assigned; start somewhere realistic-looking.
_FIRST_NUMBER = 100000000000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Project:
    """A GCP project. Its resource ``name`` is ``projects/<number>``."""

    project_id: str
    number: int
    display_name: str = ""
    parent: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    state: str = "ACTIVE"
    create_time: str = field(default_factory=_now)

    @property
    def name(self) -> str:
        return f"projects/{self.number}"

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "name": self.name,
            "projectId": self.project_id,
            "state": self.state,
            "createTime": self.create_time,
            "updateTime": self.create_time,
            "etag": f"etag-{self.number}",
        }
        if self.display_name:
            resource["displayName"] = self.display_name
        if self.parent:
            resource["parent"] = self.parent
        if self.labels:
            resource["labels"] = self.labels
        return resource


class ResourceManagerBackend(BaseBackend):
    """In-memory Resource Manager (Projects) state."""

    def setup(self) -> None:
        self.projects: dict[str, Project] = {}  # keyed by project_id
        self.numbers: dict[int, str] = {}  # project number -> project_id
        self.operations: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self._number_seq = _FIRST_NUMBER

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _operation(self, resource: dict[str, Any]) -> dict[str, Any]:
        name = f"operations/op-{self._next()}"
        operation = {
            "name": name,
            "done": True,
            "response": {"@type": _PROJECT_TYPE, **resource},
        }
        self.operations[name] = operation
        return operation

    def get_operation(self, name: str) -> dict[str, Any]:
        return self.operations.get(name, {"name": name, "done": True})

    def _resolve(self, ident: str) -> Project:
        """Resolve a project by its id or its assigned number."""
        if ident in self.projects:
            return self.projects[ident]
        if ident.isdigit():
            project_id = self.numbers.get(int(ident))
            if project_id is not None:
                return self.projects[project_id]
        raise exceptions.not_found(f"Project not found: projects/{ident}")

    # -- projects ----------------------------------------------------------

    def create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = body.get("projectId")
        if not project_id:
            raise exceptions.bad_request("Project field 'projectId' is required")
        if project_id in self.projects:
            raise exceptions.already_exists(f"Project already exists: {project_id}")
        self._number_seq += 1
        project = Project(
            project_id=project_id,
            number=self._number_seq,
            display_name=body.get("displayName", ""),
            parent=body.get("parent", ""),
            labels=dict(body.get("labels") or {}),
        )
        self.projects[project_id] = project
        self.numbers[project.number] = project_id
        return self._operation(project.to_resource())

    def get_project(self, ident: str) -> Project:
        return self._resolve(ident)

    def list_projects(self, parent: str | None) -> list[Project]:
        projects = [p for p in self.projects.values() if p.state != "DELETE_REQUESTED"]
        if parent:
            projects = [p for p in projects if p.parent == parent]
        return sorted(projects, key=lambda p: p.project_id)

    def search_projects(self) -> list[Project]:
        return sorted(
            (p for p in self.projects.values() if p.state == "ACTIVE"),
            key=lambda p: p.project_id,
        )

    def delete_project(self, ident: str) -> dict[str, Any]:
        project = self._resolve(ident)
        project.state = "DELETE_REQUESTED"
        return self._operation(project.to_resource())

    def undelete_project(self, ident: str) -> dict[str, Any]:
        project = self._resolve(ident)
        project.state = "ACTIVE"
        return self._operation(project.to_resource())

    def update_project(self, ident: str, body: dict[str, Any]) -> dict[str, Any]:
        project = self._resolve(ident)
        if "displayName" in body:
            project.display_name = body["displayName"]
        if "labels" in body:
            project.labels = dict(body["labels"] or {})
        return self._operation(project.to_resource())


#: Global-namespace backend (projects are not sharded by an enclosing project);
#: inspect via ``get_backend("resourcemanager")[anything]``.
resourcemanager_backends: BackendDict[ResourceManagerBackend] = BackendDict(
    ResourceManagerBackend, "resourcemanager", global_namespace=True
)
