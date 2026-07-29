"""IAM Admin tests using the real (gRPC-only) client, served by drongo.

IAM's client ships no REST transport and honors no emulator env var, so drongo
runs an in-process gRPC server and injects a transport into the default client.
"""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project"


def _client():
    from google.cloud import iam_admin_v1 as iam

    return iam.IAMClient()


def _create(client, account_id="svc1", **sa):
    return client.create_service_account(
        request={"name": PARENT, "account_id": account_id, "service_account": sa}
    )


# -- service accounts -------------------------------------------------------


def test_create_and_get() -> None:
    client = _client()
    sa = _create(client, display_name="My SVC")
    assert sa.email == "svc1@test-project.iam.gserviceaccount.com"
    assert sa.name.endswith(
        "/serviceAccounts/svc1@test-project.iam.gserviceaccount.com"
    )
    assert (
        client.get_service_account(request={"name": sa.name}).display_name == "My SVC"
    )


def test_get_by_unique_id() -> None:
    client = _client()
    sa = _create(client)
    by_uid = client.get_service_account(
        request={"name": f"{PARENT}/serviceAccounts/{sa.unique_id}"}
    )
    assert by_uid.email == sa.email


def test_duplicate_conflicts() -> None:
    client = _client()
    _create(client)
    with pytest.raises(gexc.AlreadyExists):
        _create(client)


def test_get_missing_not_found() -> None:
    client = _client()
    with pytest.raises(gexc.NotFound):
        client.get_service_account(
            request={
                "name": f"{PARENT}/serviceAccounts/ghost@x.iam.gserviceaccount.com"
            }
        )


def test_list_and_delete() -> None:
    client = _client()
    _create(client, "a")
    _create(client, "b")
    emails = sorted(
        a.email.split("@")[0]
        for a in client.list_service_accounts(request={"name": PARENT}).accounts
    )
    assert emails == ["a", "b"]

    sa = client.get_service_account(
        request={
            "name": f"{PARENT}/serviceAccounts/a@test-project.iam.gserviceaccount.com"
        }
    )
    client.delete_service_account(request={"name": sa.name})
    with pytest.raises(gexc.NotFound):
        client.get_service_account(request={"name": sa.name})


def test_disable_and_enable() -> None:
    client = _client()
    sa = _create(client)
    client.disable_service_account(request={"name": sa.name})
    assert client.get_service_account(request={"name": sa.name}).disabled is True
    client.enable_service_account(request={"name": sa.name})
    assert client.get_service_account(request={"name": sa.name}).disabled is False


# -- keys -------------------------------------------------------------------


def test_key_lifecycle() -> None:
    client = _client()
    sa = _create(client)

    key = client.create_service_account_key(request={"name": sa.name})
    assert key.name.startswith(f"{sa.name}/keys/")
    assert key.private_key_data  # the API returns key material on create

    keys = client.list_service_account_keys(request={"name": sa.name}).keys
    assert [k.name for k in keys] == [key.name]
    assert client.get_service_account_key(request={"name": key.name}).name == key.name

    client.delete_service_account_key(request={"name": key.name})
    assert client.list_service_account_keys(request={"name": sa.name}).keys == []


def test_backend_is_inspectable() -> None:
    client = _client()
    _create(client, "inspect")
    accounts = get_backend("iam")["test-project"].service_accounts
    assert "inspect@test-project.iam.gserviceaccount.com" in accounts
