"""In-memory models for Google Cloud Secret Manager."""

from __future__ import annotations

from dataclasses import dataclass, field

from gato.core import exceptions
from gato.core.backend import BackendDict, BaseBackend
from gato.core.utils import now_rfc3339


@dataclass
class SecretVersion:
    """One version of a secret's payload."""

    project: str
    secret_id: str
    version: int
    data: bytes
    state: str = "ENABLED"  # ENABLED | DISABLED | DESTROYED
    create_time: str = field(default_factory=now_rfc3339)

    @property
    def name(self) -> str:
        return (
            f"projects/{self.project}/secrets/{self.secret_id}/versions/{self.version}"
        )

    def to_resource(self) -> dict:
        return {
            "name": self.name,
            "createTime": self.create_time,
            "state": self.state,
            "etag": f'"{self.version}"',
        }


@dataclass
class Secret:
    """A secret container plus its ordered versions."""

    project: str
    secret_id: str
    replication: dict = field(default_factory=lambda: {"automatic": {}})
    labels: dict[str, str] = field(default_factory=dict)
    create_time: str = field(default_factory=now_rfc3339)
    versions: list[SecretVersion] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"projects/{self.project}/secrets/{self.secret_id}"

    def to_resource(self) -> dict:
        resource: dict = {
            "name": self.name,
            "replication": self.replication or {"automatic": {}},
            "createTime": self.create_time,
            "etag": f'"{len(self.versions)}"',
        }
        if self.labels:
            resource["labels"] = dict(self.labels)
        return resource


class SecretManagerBackend(BaseBackend):
    """In-memory Secret Manager state for a single project."""

    def setup(self) -> None:
        # Keyed by secret_id (the backend is already project-scoped).
        self.secrets: dict[str, Secret] = {}

    # -- secrets -----------------------------------------------------------

    def create_secret(
        self,
        secret_id: str,
        *,
        replication: dict | None = None,
        labels: dict[str, str] | None = None,
    ) -> Secret:
        if secret_id in self.secrets:
            raise exceptions.already_exists(f"Secret [{secret_id}] already exists.")
        secret = Secret(
            project=self.project,
            secret_id=secret_id,
            replication=replication or {"automatic": {}},
            labels=dict(labels or {}),
        )
        self.secrets[secret_id] = secret
        return secret

    def get_secret(self, secret_id: str) -> Secret:
        try:
            return self.secrets[secret_id]
        except KeyError:
            raise exceptions.not_found(
                f"Secret [projects/{self.project}/secrets/{secret_id}] not found."
            )

    def list_secrets(self) -> list[Secret]:
        return [self.secrets[key] for key in sorted(self.secrets)]

    def delete_secret(self, secret_id: str) -> None:
        self.get_secret(secret_id)
        del self.secrets[secret_id]

    # -- versions ----------------------------------------------------------

    def add_version(self, secret_id: str, data: bytes) -> SecretVersion:
        secret = self.get_secret(secret_id)
        version = SecretVersion(
            project=self.project,
            secret_id=secret_id,
            version=len(secret.versions) + 1,
            data=data,
        )
        secret.versions.append(version)
        return version

    def _resolve_version(self, secret: Secret, version: str) -> SecretVersion:
        if version in ("latest", ""):
            for candidate in reversed(secret.versions):
                if candidate.state == "ENABLED":
                    return candidate
            raise exceptions.not_found(
                f"Secret Version [{secret.name}/versions/latest] not found."
            )
        try:
            index = int(version) - 1
            if index < 0:
                raise IndexError
            return secret.versions[index]
        except (ValueError, IndexError):
            raise exceptions.not_found(
                f"Secret Version [{secret.name}/versions/{version}] not found."
            )

    def get_version(self, secret_id: str, version: str) -> SecretVersion:
        return self._resolve_version(self.get_secret(secret_id), version)

    def list_versions(self, secret_id: str) -> list[SecretVersion]:
        return list(self.get_secret(secret_id).versions)

    def access_version(self, secret_id: str, version: str) -> SecretVersion:
        secret_version = self.get_version(secret_id, version)
        if secret_version.state != "ENABLED":
            raise exceptions.GatoHttpError(
                400,
                f"Cannot access secret version in state {secret_version.state}.",
                reason="failedPrecondition",
                status="FAILED_PRECONDITION",
            )
        return secret_version

    def set_version_state(
        self, secret_id: str, version: str, state: str
    ) -> SecretVersion:
        secret_version = self.get_version(secret_id, version)
        secret_version.state = state
        if state == "DESTROYED":
            secret_version.data = b""
        return secret_version


#: Project-keyed backends, inspectable via ``get_backend("secretmanager")[p]``.
secretmanager_backends: BackendDict[SecretManagerBackend] = BackendDict(
    SecretManagerBackend, "secretmanager"
)
