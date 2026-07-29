# Secret Manager

- **Client:** `google-cloud-secret-manager`
- **Transport:** gRPC (the client default). drongo forces the client onto its
  **REST** transport for the mock scope, so no code change is needed.
- **Backend:** per-project.

Use the **normal** client, with no `transport` argument.

!!! note "Why forced REST?"
    Secret Manager's default client speaks gRPC, which can't be intercepted over
    HTTP. The client also ships a REST transport, so drongo transparently
    switches the client to `transport="rest"` while a mock scope is active and
    serves it from the in-memory backend. Your application code stays exactly as
    it is in production.

## Secrets and versions

```python
from drongo import mock_gcp


@mock_gcp
def test_secret():
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()  # default, no transport arg
    secret = client.create_secret(
        request={
            "parent": "projects/my-project",
            "secret_id": "api-key",
            "secret": {"replication": {"automatic": {}}},
        }
    )
    client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"s3cr3t"}}
    )

    accessed = client.access_secret_version(
        request={"name": f"{secret.name}/versions/latest"}
    )
    assert accessed.payload.data == b"s3cr3t"
```

## Enable, disable, destroy

```python
@mock_gcp
def test_version_lifecycle():
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    secret = client.create_secret(
        request={
            "parent": "projects/p",
            "secret_id": "token",
            "secret": {"replication": {"automatic": {}}},
        }
    )
    version = client.add_secret_version(
        request={"parent": secret.name, "payload": {"data": b"v1"}}
    )

    client.disable_secret_version(request={"name": version.name})
    client.enable_secret_version(request={"name": version.name})
    client.destroy_secret_version(request={"name": version.name})
```

## Listing and deleting

```python
@mock_gcp
def test_list_delete():
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    for secret_id in ("a", "b"):
        client.create_secret(
            request={
                "parent": "projects/p",
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )

    names = [
        s.name.rsplit("/", 1)[-1] for s in client.list_secrets(parent="projects/p")
    ]
    assert sorted(names) == ["a", "b"]

    client.delete_secret(request={"name": "projects/p/secrets/a"})
```

## Per-project isolation

Secrets are scoped per project, so the same secret id in two projects does not
collide:

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_isolation():
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    for project in ("alpha", "beta"):
        client.create_secret(
            request={
                "parent": f"projects/{project}",
                "secret_id": "shared-name",
                "secret": {"replication": {"automatic": {}}},
            }
        )

    assert "shared-name" in get_backend("secretmanager")["alpha"].secrets
    assert "shared-name" in get_backend("secretmanager")["beta"].secrets
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete secret | Supported |
| Update secret (labels) | Partial |
| Add / get / list versions | Supported |
| Access version (incl. `latest`) | Supported |
| Enable / disable / destroy version | Supported |
| IAM policy | Planned |
