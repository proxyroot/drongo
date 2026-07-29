"""Resource Manager (Projects v3) tests using the default client (forced REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")


def _client():
    from google.cloud import resourcemanager_v3 as rm

    return rm.ProjectsClient()


def _create(client, project_id: str, **fields):
    project = {"project_id": project_id, **fields}
    return client.create_project(request={"project": project}).result(timeout=10)


# -- create / get -----------------------------------------------------------


def test_create_and_get_project() -> None:
    client = _client()
    created = _create(client, "my-app", display_name="My App")
    assert created.project_id == "my-app"
    assert created.name.startswith("projects/")
    assert created.display_name == "My App"

    fetched = client.get_project(request={"name": "projects/my-app"})
    assert fetched.project_id == "my-app"


def test_get_by_project_number() -> None:
    client = _client()
    created = _create(client, "my-app")
    # v3 resource name is projects/<number>; addressing by it also works.
    assert client.get_project(request={"name": created.name}).project_id == "my-app"


def test_duplicate_project_conflicts() -> None:
    client = _client()
    _create(client, "dup")
    with pytest.raises(gexc.Conflict):
        _create(client, "dup")


def test_get_missing_project_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_project(request={"name": "projects/ghost"})


# -- list / search ----------------------------------------------------------


def test_list_projects_by_parent() -> None:
    client = _client()
    _create(client, "a", parent="folders/42")
    _create(client, "b", parent="folders/42")
    _create(client, "c", parent="folders/99")

    names = sorted(
        p.project_id for p in client.list_projects(request={"parent": "folders/42"})
    )
    assert names == ["a", "b"]


def test_list_hides_deleted() -> None:
    client = _client()
    _create(client, "keep", parent="folders/1")
    _create(client, "gone", parent="folders/1")
    client.delete_project(request={"name": "projects/gone"}).result(timeout=10)

    names = [
        p.project_id for p in client.list_projects(request={"parent": "folders/1"})
    ]
    assert names == ["keep"]


def test_search_projects() -> None:
    client = _client()
    _create(client, "one")
    _create(client, "two")
    found = sorted(p.project_id for p in client.search_projects(request={}))
    assert found == ["one", "two"]


# -- delete / undelete / update --------------------------------------------


def test_delete_marks_delete_requested() -> None:
    client = _client()
    _create(client, "temp")
    client.delete_project(request={"name": "projects/temp"}).result(timeout=10)
    assert (
        client.get_project(request={"name": "projects/temp"}).state.name
        == "DELETE_REQUESTED"
    )


def test_undelete_restores_active() -> None:
    client = _client()
    _create(client, "temp")
    client.delete_project(request={"name": "projects/temp"}).result(timeout=10)
    client.undelete_project(request={"name": "projects/temp"}).result(timeout=10)
    assert client.get_project(request={"name": "projects/temp"}).state.name == "ACTIVE"


def test_update_display_name_and_labels() -> None:
    from google.cloud import resourcemanager_v3 as rm

    client = _client()
    _create(client, "proj", display_name="Old")

    project = rm.Project(
        name="projects/proj", display_name="New", labels={"env": "prod"}
    )
    updated = client.update_project(
        request={
            "project": project,
            "update_mask": {"paths": ["display_name", "labels"]},
        }
    ).result(timeout=10)
    assert updated.display_name == "New"
    assert dict(updated.labels) == {"env": "prod"}


def test_backend_is_inspectable() -> None:
    client = _client()
    _create(client, "inspect-me")
    assert "inspect-me" in get_backend("resourcemanager")["_"].projects
