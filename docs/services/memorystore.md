# Memorystore (Redis)

- **Client:** `google-cloud-redis` (`redis_v1.CloudRedisClient`)
- **Transport:** gRPC (the client default), forced to **REST** during a mock scope.
- **Backend:** per-project.

Use the **normal** client with no `transport` argument. Scoped to **instance
administration** (the control plane).

!!! note "Control plane only"
    drongo mocks provisioning and managing Redis **instances**, not the Redis
    data plane. Instance mutations (`create`/`update`/`delete`) are long-running
    operations completed synchronously, so `.result()` returns immediately with a
    `READY` instance. To exercise Redis commands, point a Redis client at a real
    or local Redis.

## Instances

```python
from drongo import mock_gcp


@mock_gcp
def test_instances():
    from google.cloud import redis_v1

    client = redis_v1.CloudRedisClient()
    parent = "projects/my-project/locations/us-central1"

    instance = redis_v1.Instance(
        tier=redis_v1.Instance.Tier.BASIC,
        memory_size_gb=1,
        display_name="Cache",
    )
    created = client.create_instance(
        request={"parent": parent, "instance_id": "cache", "instance": instance}
    ).result()
    assert created.state.name == "READY"
    assert created.host and created.port == 6379

    assert client.get_instance(request={"name": created.name}).display_name == "Cache"
    client.delete_instance(request={"name": created.name}).result()
```

`list_instances` and `update_instance` are also supported.

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete instance (LRO) | Supported |
| Update instance (LRO) | Supported |
| Failover / export / import / upgrade | Planned |
| Redis data plane (GET/SET/...) | Out of scope (use a real Redis) |
