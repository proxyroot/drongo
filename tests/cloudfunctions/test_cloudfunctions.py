"""Cloud Functions (2nd gen) tests using the default client (forced REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"


def _client():
    from google.cloud import functions_v2

    return functions_v2.FunctionServiceClient()


def _function(runtime="python312", entry="main"):
    from google.cloud import functions_v2

    return functions_v2.Function(
        build_config=functions_v2.BuildConfig(runtime=runtime, entry_point=entry)
    )


def _create(client, function_id="hello", **fields):
    return client.create_function(
        request={
            "parent": PARENT,
            "function_id": function_id,
            "function": _function(**fields),
        }
    ).result(timeout=10)


def test_create_and_get() -> None:
    client = _client()
    created = _create(client)
    assert created.name == f"{PARENT}/functions/hello"
    assert created.state.name == "ACTIVE"
    assert created.url

    got = client.get_function(request={"name": created.name})
    assert got.build_config.runtime == "python312"
    assert got.build_config.entry_point == "main"


def test_duplicate_conflicts() -> None:
    client = _client()
    _create(client)
    with pytest.raises(gexc.Conflict):
        _create(client)


def test_get_missing_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_function(request={"name": f"{PARENT}/functions/ghost"})


def test_list_and_delete() -> None:
    client = _client()
    _create(client, "a")
    _create(client, "b")
    names = sorted(
        f.name.rsplit("/", 1)[-1]
        for f in client.list_functions(request={"parent": PARENT})
    )
    assert names == ["a", "b"]

    client.delete_function(request={"name": f"{PARENT}/functions/a"}).result(timeout=10)
    with pytest.raises(gexc.NotFound):
        client.get_function(request={"name": f"{PARENT}/functions/a"})


def test_update_function() -> None:
    client = _client()
    _create(client, "hello")
    from google.cloud import functions_v2

    updated = client.update_function(
        request={
            "function": functions_v2.Function(
                name=f"{PARENT}/functions/hello",
                description="now with a description",
            ),
            "update_mask": {"paths": ["description"]},
        }
    ).result(timeout=10)
    assert updated.description == "now with a description"


def test_generate_upload_url() -> None:
    client = _client()
    resp = client.generate_upload_url(request={"parent": PARENT})
    assert resp.upload_url
    assert resp.storage_source.bucket


def test_backend_is_inspectable() -> None:
    client = _client()
    _create(client, "inspect")
    functions = get_backend("cloudfunctions")["test-project"].functions
    assert f"{PARENT}/functions/inspect" in functions
