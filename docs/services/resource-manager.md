# Resource Manager

- **Client:** `google-cloud-resource-manager` (`resourcemanager_v3.ProjectsClient`)
- **Transport:** gRPC (the client default). drongo forces the client onto its
  **REST** transport for the mock scope.
- **Backend:** global namespace (projects are not sharded by an enclosing project).

Use the **normal** client with no `transport` argument. Scoped to the **Projects**
API, the most-used part of Resource Manager.

!!! note "Long-running operations complete synchronously"
    `create_project`, `delete_project`, `update_project`, and `undelete_project`
    return a **long-running operation** (LRO). drongo completes each one
    synchronously and returns a *done* operation, so `.result()` returns
    immediately with the `Project`. Errors surface as REST-style exceptions (a
    duplicate project raises `Conflict`).

## Create and get a project

`create_project` assigns a project number; the resource `name` is
`projects/<number>`. You can address a project by that number **or** by its
`project_id`:

```python
from drongo import mock_gcp


@mock_gcp
def test_project():
    from google.cloud import resourcemanager_v3 as rm

    client = rm.ProjectsClient()

    created = client.create_project(
        request={"project": {"project_id": "my-app", "display_name": "My App"}}
    ).result()
    assert created.project_id == "my-app"
    assert created.name.startswith("projects/")

    # Addressable by project_id or by projects/<number>.
    assert (
        client.get_project(request={"name": "projects/my-app"}).display_name == "My App"
    )
    assert client.get_project(request={"name": created.name}).project_id == "my-app"
```

## List and search

`list_projects` filters by `parent` (an organization or folder). `search_projects`
returns active projects:

```python
@mock_gcp
def test_list():
    from google.cloud import resourcemanager_v3 as rm

    client = rm.ProjectsClient()
    client.create_project(
        request={"project": {"project_id": "a", "parent": "folders/42"}}
    ).result()
    client.create_project(
        request={"project": {"project_id": "b", "parent": "folders/42"}}
    ).result()

    listed = client.list_projects(request={"parent": "folders/42"})
    assert sorted(p.project_id for p in listed) == ["a", "b"]
```

## Delete, undelete, update

`delete_project` moves the project to `DELETE_REQUESTED` (and hides it from
`list_projects`); `undelete_project` restores it to `ACTIVE`:

```python
@mock_gcp
def test_lifecycle():
    from google.cloud import resourcemanager_v3 as rm

    client = rm.ProjectsClient()
    client.create_project(request={"project": {"project_id": "temp"}}).result()

    client.delete_project(request={"name": "projects/temp"}).result()
    assert (
        client.get_project(request={"name": "projects/temp"}).state.name
        == "DELETE_REQUESTED"
    )

    client.undelete_project(request={"name": "projects/temp"}).result()
    assert client.get_project(request={"name": "projects/temp"}).state.name == "ACTIVE"
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get project | Supported |
| Get by `project_id` or `projects/<number>` | Supported |
| List projects (by `parent`) | Supported |
| Search projects | Supported |
| Delete / undelete project | Supported |
| Update project (display name, labels) | Supported |
| Move project, IAM policy, tags | Planned |
| Folders, Organizations | Planned |
