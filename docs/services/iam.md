# IAM & Service Accounts

- **Client:** `google-cloud-iam` (`iam_admin_v1.IAMClient`)
- **Transport:** gRPC only. The client ships **no REST transport** and honors **no
  emulator env var**, so drongo runs an in-process gRPC server and injects a
  transport pointing the default client at it.
- **Backend:** per-project.

Use the **normal** client with no `transport` argument. Scoped to **service
accounts and their keys**.

!!! note "A third interception mode"
    Most gRPC-first GCP services are handled by forcing the client onto its REST
    transport (Secret Manager, Cloud Tasks, ...) or by an emulator env var
    (Pub/Sub, Firestore). IAM Admin has neither, so drongo introduces a third
    mode: it starts the in-process gRPC server and **injects a transport** built
    on an insecure channel to it during the mock scope. Your code still just
    calls `IAMClient()`.

## Service accounts

```python
from drongo import mock_gcp


@mock_gcp
def test_service_accounts():
    from google.cloud import iam_admin_v1 as iam

    client = iam.IAMClient()
    parent = "projects/my-project"

    sa = client.create_service_account(
        request={
            "name": parent,
            "account_id": "worker",
            "service_account": {"display_name": "Worker"},
        }
    )
    assert sa.email == "worker@my-project.iam.gserviceaccount.com"

    # Addressable by email or by unique id.
    assert (
        client.get_service_account(request={"name": sa.name}).display_name == "Worker"
    )
    by_uid = client.get_service_account(
        request={"name": f"{parent}/serviceAccounts/{sa.unique_id}"}
    )
    assert by_uid.email == sa.email
```

`list_service_accounts`, `delete_service_account`, and
`enable_service_account` / `disable_service_account` all work as expected;
duplicates raise `AlreadyExists`, missing accounts raise `NotFound`.

## Keys

`create_service_account_key` returns key material (a fake but non-empty blob, as
the real API does):

```python
@mock_gcp
def test_keys():
    from google.cloud import iam_admin_v1 as iam

    client = iam.IAMClient()
    sa = client.create_service_account(
        request={"name": "projects/p", "account_id": "svc", "service_account": {}}
    )

    key = client.create_service_account_key(request={"name": sa.name})
    assert key.private_key_data

    assert [
        k.name for k in client.list_service_account_keys(request={"name": sa.name}).keys
    ] == [key.name]
    client.delete_service_account_key(request={"name": key.name})
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete service account | Supported |
| Get by email or unique id | Supported |
| Enable / disable service account | Supported |
| Create / list / get / delete key | Supported |
| Update (display name / description) | Planned |
| Roles (custom roles, `QueryGrantableRoles`) | Planned |
| IAM policy get/set (`getIamPolicy`/`setIamPolicy`) | Planned |
| `SignBlob` / `SignJwt` (IAM Credentials API) | Planned |
