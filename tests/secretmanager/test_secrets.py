"""Secret Manager tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "projects/test-project"


def _client():
    from google.cloud import secretmanager

    # No transport="rest": drongo forces the default client onto REST.
    return secretmanager.SecretManagerServiceClient()


def _create(client, secret_id: str = "api-key"):
    return client.create_secret(
        request={
            "parent": PROJECT,
            "secret_id": secret_id,
            "secret": {"replication": {"automatic": {}}},
        }
    )


def test_create_and_get_secret() -> None:
    client = _client()
    secret = _create(client)
    assert secret.name == f"{PROJECT}/secrets/api-key"
    assert client.get_secret(request={"name": secret.name}).name == secret.name


def test_duplicate_secret_conflicts() -> None:
    client = _client()
    _create(client, "dup")
    # The REST transport surfaces HTTP 409 as Conflict (AlreadyExists is its
    # gRPC-status subclass, which the JSON API does not distinguish).
    with pytest.raises(gexc.Conflict):
        _create(client, "dup")


def test_add_and_access_versions() -> None:
    client = _client()
    secret = _create(client)

    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"one"}}
    )
    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"two"}}
    )

    latest = client.access_secret_version(
        request={"name": f"{secret.name}/versions/latest"}
    )
    assert latest.payload.data == b"two"

    first = client.access_secret_version(request={"name": f"{secret.name}/versions/1"})
    assert first.payload.data == b"one"


def test_list_secrets_and_versions() -> None:
    client = _client()
    secret = _create(client, "listable")
    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"v"}}
    )

    names = [s.name for s in client.list_secrets(request={"parent": PROJECT})]
    assert secret.name in names

    versions = list(client.list_secret_versions(request={"parent": secret.name}))
    assert len(versions) == 1


def test_destroyed_version_cannot_be_accessed() -> None:
    client = _client()
    secret = _create(client, "destroyable")
    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"gone"}}
    )
    client.destroy_secret_version(request={"name": f"{secret.name}/versions/1"})

    with pytest.raises(gexc.BadRequest):
        client.access_secret_version(request={"name": f"{secret.name}/versions/1"})


def test_delete_secret() -> None:
    client = _client()
    secret = _create(client, "deletable")
    client.delete_secret(request={"name": secret.name})
    with pytest.raises(gexc.NotFound):
        client.get_secret(request={"name": secret.name})


def test_access_missing_secret_raises() -> None:
    client = _client()
    with pytest.raises(gexc.NotFound):
        client.access_secret_version(
            request={"name": f"{PROJECT}/secrets/ghost/versions/latest"}
        )


def test_secrets_are_isolated_per_project() -> None:
    from drongo import get_backend

    client = _client()
    client.create_secret(
        request={
            "parent": "projects/alpha",
            "secret_id": "shared-name",
            "secret": {"replication": {"automatic": {}}},
        }
    )

    # A different project has its own backend (moto-style BackendDict keying).
    beta = list(client.list_secrets(request={"parent": "projects/beta"}))
    assert beta == []
    assert "shared-name" in get_backend("secretmanager")["alpha"].secrets
    assert "shared-name" not in get_backend("secretmanager")["beta"].secrets
