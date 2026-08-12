# Artifact Registry

- **Client:** `google-cloud-artifact-registry` (`artifactregistry_v1.ArtifactRegistryClient`)
- **Transport:** gRPC (the client default), forced to REST during a mock scope.
  Artifact Registry has no emulator env var, so drongo forces the client onto its
  REST transport and serves it from the HTTP layer.
- **Backend:** per-project.

Use the normal client with no `transport` argument.

Repositories and tags have full CRUD through the client. Packages, versions and
files have no create RPC (they come from *pushed* artifacts), so seed them with
the backend helpers and then read/delete them through the client.

## Repositories

```python
from drongo import mock_gcp


@mock_gcp
def test_repositories():
    from google.cloud import artifactregistry_v1

    parent = "projects/my-project/locations/us"
    client = artifactregistry_v1.ArtifactRegistryClient()

    repo = client.create_repository(
        parent=parent,
        repository_id="images",
        repository=artifactregistry_v1.Repository(
            format_=artifactregistry_v1.Repository.Format.DOCKER
        ),
    ).result()  # the create LRO completes synchronously

    assert client.get_repository(name=repo.name).name == repo.name
    assert [r.name for r in client.list_repositories(parent=parent)] == [repo.name]
```

## Packages, versions, files, tags

Seed packages / versions / files via `get_backend("artifactregistry")[project]`,
then read them through the client. Tags are created through the client:

```python
from drongo import get_backend, mock_gcp


@mock_gcp
def test_packages_and_tags():
    from google.cloud import artifactregistry_v1

    parent = "projects/my-project/locations/us"
    client = artifactregistry_v1.ArtifactRegistryClient()
    repo = client.create_repository(
        parent=parent,
        repository_id="images",
        repository=artifactregistry_v1.Repository(),
    ).result()

    backend = get_backend("artifactregistry")["my-project"]
    backend.add_package(repo.name, "web", display_name="web")
    package = f"{repo.name}/packages/web"
    backend.add_version(package, "sha256:abc")

    assert [p.name for p in client.list_packages(parent=repo.name)] == [package]

    tag = client.create_tag(
        parent=package,
        tag_id="latest",
        tag=artifactregistry_v1.Tag(version=f"{package}/versions/sha256:abc"),
    )
    assert client.get_tag(name=tag.name).version.endswith("sha256:abc")
```

Missing resources raise `google.api_core.exceptions.NotFound`; a duplicate
repository raises `Conflict` (REST-style, since the client is forced onto REST).

## Coverage

| Operation | Status |
| --- | --- |
| Repositories: create / get / list / update / delete (LRO) | Supported |
| Tags: create / get / list / update / delete | Supported |
| Packages: list / get / delete (LRO), seed via backend | Supported |
| Versions: list / get / delete (LRO), seed via backend | Supported |
| Files: list / get, seed via backend | Supported |
| Artifact upload/download, IAM, format-specific APIs | Planned |
