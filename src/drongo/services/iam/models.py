"""In-memory models for IAM Admin (service accounts and their keys).

IAM Admin's client is gRPC-only with no REST transport and no emulator env var,
so drongo serves it from an in-process gRPC emulator (see emulator.py) and points
the client at it by injecting a transport (see ``force_local_grpc_patchers``).

Values are kept as plain Python here; the emulator, which owns the IAM proto
types, converts to/from them. Backends are per project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["IAMBackend", "ServiceAccount", "ServiceAccountKey", "iam_backends"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ServiceAccountKey:
    """A key belonging to a service account."""

    key_id: str
    service_account_name: str
    private_key_type: int = 0
    key_algorithm: int = 0
    private_key_data: bytes = b""
    public_key_data: bytes = b""
    disabled: bool = False

    @property
    def name(self) -> str:
        return f"{self.service_account_name}/keys/{self.key_id}"


@dataclass
class ServiceAccount:
    """A service account and the keys it owns."""

    project: str
    account_id: str
    unique_id: str
    display_name: str = ""
    description: str = ""
    disabled: bool = False
    keys: dict[str, ServiceAccountKey] = field(default_factory=dict)

    @property
    def email(self) -> str:
        return f"{self.account_id}@{self.project}.iam.gserviceaccount.com"

    @property
    def name(self) -> str:
        return f"projects/{self.project}/serviceAccounts/{self.email}"


class IAMBackend(BaseBackend):
    """In-memory IAM Admin state for a single project."""

    def setup(self) -> None:
        self.service_accounts: dict[str, ServiceAccount] = {}  # keyed by email
        self.unique_ids: dict[str, str] = {}  # unique_id -> email
        self._uid_seq = 100000000000000000000
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _resolve(self, identifier: str) -> ServiceAccount:
        """Resolve a service account by its email or its unique id."""
        if identifier in self.service_accounts:
            return self.service_accounts[identifier]
        email = self.unique_ids.get(identifier)
        if email is not None:
            return self.service_accounts[email]
        raise exceptions.not_found(f"Service account does not exist: {identifier}")

    # -- service accounts --------------------------------------------------

    def create_service_account(
        self, account_id: str, display_name: str, description: str
    ) -> ServiceAccount:
        if not account_id:
            raise exceptions.bad_request("account_id is required")
        email = f"{account_id}@{self.project}.iam.gserviceaccount.com"
        if email in self.service_accounts:
            raise exceptions.already_exists(f"Service account already exists: {email}")
        self._uid_seq += 1
        account = ServiceAccount(
            project=self.project,
            account_id=account_id,
            unique_id=str(self._uid_seq),
            display_name=display_name,
            description=description,
        )
        self.service_accounts[email] = account
        self.unique_ids[account.unique_id] = email
        return account

    def get_service_account(self, identifier: str) -> ServiceAccount:
        return self._resolve(identifier)

    def list_service_accounts(self) -> list[ServiceAccount]:
        return sorted(self.service_accounts.values(), key=lambda a: a.email)

    def delete_service_account(self, identifier: str) -> None:
        account = self._resolve(identifier)
        self.unique_ids.pop(account.unique_id, None)
        del self.service_accounts[account.email]

    def set_disabled(self, identifier: str, disabled: bool) -> ServiceAccount:
        account = self._resolve(identifier)
        account.disabled = disabled
        return account

    # -- keys --------------------------------------------------------------

    def create_key(
        self, identifier: str, private_key_type: int, key_algorithm: int
    ) -> ServiceAccountKey:
        account = self._resolve(identifier)
        key_id = f"{self._next():040x}"
        key = ServiceAccountKey(
            key_id=key_id,
            service_account_name=account.name,
            private_key_type=private_key_type,
            key_algorithm=key_algorithm,
            # A fake but non-empty private key blob, as the real API returns one.
            private_key_data=f"drongo-fake-private-key-{key_id}".encode(),
            public_key_data=f"drongo-fake-public-key-{key_id}".encode(),
        )
        account.keys[key_id] = key
        return key

    def list_keys(self, identifier: str) -> list[ServiceAccountKey]:
        account = self._resolve(identifier)
        return sorted(account.keys.values(), key=lambda k: k.key_id)

    def get_key(self, identifier: str, key_id: str) -> ServiceAccountKey:
        account = self._resolve(identifier)
        try:
            return account.keys[key_id]
        except KeyError:
            raise exceptions.not_found(f"Key does not exist: {key_id}")

    def delete_key(self, identifier: str, key_id: str) -> None:
        account = self._resolve(identifier)
        if key_id not in account.keys:
            raise exceptions.not_found(f"Key does not exist: {key_id}")
        del account.keys[key_id]


#: Project-keyed backends, inspectable via ``get_backend("iam")[project]``.
iam_backends: BackendDict[IAMBackend] = BackendDict(IAMBackend, "iam")
