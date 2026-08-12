"""Artifact Registry tests using the real artifactregistry_v1 client (forced REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytest.importorskip("google.cloud.artifactregistry_v1")

from drongo import get_backend  # noqa: E402

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
PARENT = f"projects/{PROJECT}/locations/us"


def _client():
    from google.cloud import artifactregistry_v1

    return artifactregistry_v1.ArtifactRegistryClient()


def _repository(client, repo_id="repo"):
    from google.cloud import artifactregistry_v1

    return client.create_repository(
        parent=PARENT,
        repository_id=repo_id,
        repository=artifactregistry_v1.Repository(
            format_=artifactregistry_v1.Repository.Format.DOCKER, description="imgs"
        ),
    ).result()  # LRO completes synchronously


# -- repositories -----------------------------------------------------------


def test_repository_create_get_list_update_delete() -> None:
    from google.cloud import artifactregistry_v1
    from google.protobuf import field_mask_pb2

    client = _client()
    repo = _repository(client)
    assert repo.name == f"{PARENT}/repositories/repo"
    assert repo.format_ == artifactregistry_v1.Repository.Format.DOCKER

    assert client.get_repository(name=repo.name).description == "imgs"
    assert [r.name for r in client.list_repositories(parent=PARENT)] == [repo.name]

    updated = client.update_repository(
        repository=artifactregistry_v1.Repository(name=repo.name, description="new"),
        update_mask=field_mask_pb2.FieldMask(paths=["description"]),
    )
    assert updated.description == "new"

    client.delete_repository(name=repo.name).result()  # LRO
    assert list(client.list_repositories(parent=PARENT)) == []


def test_duplicate_repository_conflicts() -> None:
    # Forced onto REST, so a duplicate surfaces as a REST-style Conflict (409)
    # rather than the gRPC AlreadyExists.
    client = _client()
    _repository(client)
    with pytest.raises(gexc.Conflict):
        _repository(client)


def test_get_missing_repository_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_repository(name=f"{PARENT}/repositories/ghost")


# -- packages / versions / files (seeded, no create RPC) --------------------


def test_seeded_packages_versions_files_are_readable() -> None:
    client = _client()
    repo = _repository(client)
    backend = get_backend("artifactregistry")[PROJECT]

    backend.add_package(repo.name, "mypkg", display_name="mypkg")
    package = f"{repo.name}/packages/mypkg"
    backend.add_version(package, "sha256:abc", description="v1")
    backend.add_file(repo.name, "layer.tar.gz", size_bytes="1024")

    assert [p.name for p in client.list_packages(parent=repo.name)] == [package]
    assert client.get_package(name=package).name == package

    version = f"{package}/versions/sha256:abc"
    assert [v.name for v in client.list_versions(parent=package)] == [version]
    assert client.get_version(name=version).name == version

    files = list(client.list_files(parent=repo.name))
    assert files[0].name == f"{repo.name}/files/layer.tar.gz"

    # LRO deletes.
    client.delete_version(name=version).result()
    assert list(client.list_versions(parent=package)) == []
    client.delete_package(name=package).result()
    assert list(client.list_packages(parent=repo.name)) == []


# -- tags -------------------------------------------------------------------


def test_tag_create_get_list_update_delete() -> None:
    from google.cloud import artifactregistry_v1

    client = _client()
    repo = _repository(client)
    backend = get_backend("artifactregistry")[PROJECT]
    backend.add_package(repo.name, "mypkg")
    package = f"{repo.name}/packages/mypkg"
    backend.add_version(package, "sha256:abc")

    tag = client.create_tag(
        parent=package,
        tag_id="latest",
        tag=artifactregistry_v1.Tag(version=f"{package}/versions/sha256:abc"),
    )
    assert tag.name == f"{package}/tags/latest"
    assert tag.version == f"{package}/versions/sha256:abc"

    assert client.get_tag(name=tag.name).name == tag.name
    assert [t.name for t in client.list_tags(parent=package)] == [tag.name]

    client.delete_tag(name=tag.name)
    assert list(client.list_tags(parent=package)) == []
