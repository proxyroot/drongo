"""Memorystore (Redis) tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PARENT = "projects/test-project/locations/us-central1"


def _client():
    from google.cloud import redis_v1

    return redis_v1.CloudRedisClient()


def _create(client, instance_id="cache", **fields):
    from google.cloud import redis_v1

    instance = redis_v1.Instance(
        tier=redis_v1.Instance.Tier.BASIC, memory_size_gb=1, **fields
    )
    return client.create_instance(
        request={"parent": PARENT, "instance_id": instance_id, "instance": instance}
    ).result(timeout=10)


def test_create_and_get() -> None:
    client = _client()
    created = _create(client, display_name="Cache")
    assert created.name == f"{PARENT}/instances/cache"
    assert created.state.name == "READY"
    assert created.host and created.port == 6379

    got = client.get_instance(request={"name": created.name})
    assert got.display_name == "Cache"


def test_duplicate_conflicts() -> None:
    client = _client()
    _create(client)
    with pytest.raises(gexc.Conflict):
        _create(client)


def test_get_missing_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_instance(request={"name": f"{PARENT}/instances/ghost"})


def test_list_and_delete() -> None:
    client = _client()
    _create(client, "a")
    _create(client, "b")
    names = sorted(
        i.name.rsplit("/", 1)[-1]
        for i in client.list_instances(request={"parent": PARENT})
    )
    assert names == ["a", "b"]

    client.delete_instance(request={"name": f"{PARENT}/instances/a"}).result(timeout=10)
    with pytest.raises(gexc.NotFound):
        client.get_instance(request={"name": f"{PARENT}/instances/a"})


def test_update_instance() -> None:
    from google.cloud import redis_v1

    client = _client()
    _create(client, "cache", display_name="Old")
    updated = client.update_instance(
        request={
            "instance": redis_v1.Instance(
                name=f"{PARENT}/instances/cache", display_name="New"
            ),
            "update_mask": {"paths": ["display_name"]},
        }
    ).result(timeout=10)
    assert updated.display_name == "New"


def test_backend_is_inspectable() -> None:
    client = _client()
    _create(client, "inspect")
    instances = get_backend("memorystore")["test-project"].instances
    assert f"{PARENT}/instances/inspect" in instances
