"""Storage depth: bucket IAM policy and HMAC keys, via the real client."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("drongo")

EMAIL = "svc@my-project.iam.gserviceaccount.com"


def _client():
    from google.cloud import storage

    return storage.Client(project="my-project")


# -- bucket IAM policy ------------------------------------------------------


def test_get_iam_policy_default_is_empty() -> None:
    client = _client()
    bucket = client.create_bucket("b")
    policy = bucket.get_iam_policy()
    assert list(policy) == []


def test_set_and_get_iam_policy() -> None:
    client = _client()
    bucket = client.create_bucket("b")
    policy = bucket.get_iam_policy()
    policy.bindings.append(
        {"role": "roles/storage.objectViewer", "members": {"allUsers"}}
    )
    bucket.set_iam_policy(policy)

    roles = [b["role"] for b in bucket.get_iam_policy().bindings]
    assert roles == ["roles/storage.objectViewer"]


def test_test_iam_permissions_echoes() -> None:
    client = _client()
    bucket = client.create_bucket("b")
    granted = bucket.test_iam_permissions(
        ["storage.objects.get", "storage.objects.list"]
    )
    assert set(granted) == {"storage.objects.get", "storage.objects.list"}


# -- HMAC keys --------------------------------------------------------------


def test_create_hmac_key_returns_secret() -> None:
    client = _client()
    metadata, secret = client.create_hmac_key(service_account_email=EMAIL)
    assert metadata.state == "ACTIVE"
    assert metadata.access_id
    assert secret  # the secret is only returned on create


def test_list_and_get_hmac_key() -> None:
    client = _client()
    metadata, _ = client.create_hmac_key(service_account_email=EMAIL)
    assert [k.access_id for k in client.list_hmac_keys()] == [metadata.access_id]
    assert (
        client.get_hmac_key_metadata(metadata.access_id).access_id == metadata.access_id
    )


def test_deactivate_then_delete_hmac_key() -> None:
    client = _client()
    metadata, _ = client.create_hmac_key(service_account_email=EMAIL)

    metadata.state = "INACTIVE"
    metadata.update()
    assert client.get_hmac_key_metadata(metadata.access_id).state == "INACTIVE"

    metadata.delete()
    assert list(client.list_hmac_keys()) == []


def test_delete_active_hmac_key_fails() -> None:
    from google.api_core import exceptions as gexc

    client = _client()
    metadata, _ = client.create_hmac_key(service_account_email=EMAIL)
    with pytest.raises(gexc.BadRequest):
        metadata.delete()  # still ACTIVE
