# Cloud Functions

- **Client:** `google-cloud-functions` (`functions_v2.FunctionServiceClient`)
- **Transport:** gRPC (the client default), forced to **REST** during a mock scope.
- **Backend:** per-project.

Use the **normal** client with no `transport` argument. Scoped to the **2nd-gen
admin API** (deploy / manage functions).

!!! note "No synchronous invoke"
    2nd-gen functions are invoked via their HTTP URL (they run on Cloud Run), not
    through an Admin API call, so there is no `call_function` here. drongo mocks
    the deploy/manage surface. Mutations (`create`/`update`/`delete`) are
    long-running operations completed synchronously, so `.result()` returns
    immediately.

## Deploy and manage

```python
from drongo import mock_gcp


@mock_gcp
def test_functions():
    from google.cloud import functions_v2

    client = functions_v2.FunctionServiceClient()
    parent = "projects/my-project/locations/us-central1"

    function = functions_v2.Function(
        build_config=functions_v2.BuildConfig(runtime="python312", entry_point="main"),
    )
    created = client.create_function(
        request={"parent": parent, "function_id": "hello", "function": function}
    ).result()
    assert created.state.name == "ACTIVE"
    assert created.url  # https://<region>-<project>.cloudfunctions.net/hello

    got = client.get_function(request={"name": created.name})
    assert got.build_config.runtime == "python312"

    client.delete_function(request={"name": created.name}).result()
```

`list_functions`, `update_function`, and `generate_upload_url` (a stub for the
source-upload step) are also supported.

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete function | Supported (LRO) |
| Update function | Supported (LRO) |
| `generate_upload_url` | Supported (stub) |
| Synchronous invoke | Out of scope (2nd gen has no invoke RPC) |
| 1st-gen `call_function` + executable handler | Planned |
| Source upload, `generate_download_url`, IAM policy | Planned |
