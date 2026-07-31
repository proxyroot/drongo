# Pub/Sub

- **Client:** `google-cloud-pubsub`
- **Transport:** gRPC (the client default). drongo runs an **in-process gRPC
  emulator** and points the client at it via `PUBSUB_EMULATOR_HOST`.
- **Backend:** global namespace.

Use the **normal** client with its default transport. Nothing changes.

!!! note "Why an emulator instead of forced REST?"
    Pub/Sub is gRPC-first and its behavior (publish fan-out, ack/nack) is best
    matched by speaking real gRPC. drongo starts a lightweight in-process gRPC
    server backed by the same in-memory model layer as the HTTP services, and
    redirects the client with the standard `PUBSUB_EMULATOR_HOST` env var that
    the google client already honors. Your code keeps its default transport.

## Publish and pull

```python
from drongo import mock_gcp


@mock_gcp
def test_pubsub():
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()  # default gRPC, no code change
    subscriber = pubsub_v1.SubscriberClient()
    topic = "projects/my-project/topics/orders"
    subscription = "projects/my-project/subscriptions/worker"

    publisher.create_topic(request={"name": topic})
    subscriber.create_subscription(request={"name": subscription, "topic": topic})

    publisher.publish(topic, b'{"id": 1}', kind="order").result()

    response = subscriber.pull(
        request={"subscription": subscription, "max_messages": 10}
    )
    assert response.received_messages[0].message.data == b'{"id": 1}'
    assert response.received_messages[0].message.attributes["kind"] == "order"

    subscriber.acknowledge(
        request={
            "subscription": subscription,
            "ack_ids": [response.received_messages[0].ack_id],
        }
    )
```

## Fan-out to multiple subscriptions

A published message is delivered to every subscription on the topic:

```python
@mock_gcp
def test_fanout():
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic = "projects/p/topics/events"
    publisher.create_topic(request={"name": topic})
    for sub in ("a", "b"):
        subscriber.create_subscription(
            request={"name": f"projects/p/subscriptions/{sub}", "topic": topic}
        )

    publisher.publish(topic, b"payload").result()

    for sub in ("a", "b"):
        pulled = subscriber.pull(
            request={
                "subscription": f"projects/p/subscriptions/{sub}",
                "max_messages": 10,
            }
        )
        assert pulled.received_messages[0].message.data == b"payload"
```

## Nack and redelivery

Nack a message (via `modify_ack_deadline(0)`) and it becomes available to pull
again:

```python
@mock_gcp
def test_nack_redelivers():
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic = "projects/p/topics/t"
    sub = "projects/p/subscriptions/s"
    publisher.create_topic(request={"name": topic})
    subscriber.create_subscription(request={"name": sub, "topic": topic})
    publisher.publish(topic, b"retry-me").result()

    first = subscriber.pull(request={"subscription": sub, "max_messages": 1})
    ack_id = first.received_messages[0].ack_id

    # Nack: set the ack deadline to 0 so it is redelivered immediately.
    subscriber.modify_ack_deadline(
        request={"subscription": sub, "ack_ids": [ack_id], "ack_deadline_seconds": 0}
    )

    again = subscriber.pull(request={"subscription": sub, "max_messages": 1})
    assert again.received_messages[0].message.data == b"retry-me"
```

## Async client (`gcloud.aio.pubsub`)

The async client is aiohttp/REST, not gRPC, so drongo intercepts aiohttp too and
serves it from the same backend. Publish over one transport and pull over the
other; it is one shared state. The mock scope is transport-level, so you drive
the event loop yourself (`asyncio.run` or `pytest-asyncio`).

```python
import pytest
from drongo import mock_gcp


@pytest.mark.asyncio
@mock_gcp
async def test_async_pubsub():
    from gcloud.aio.pubsub import PublisherClient, PubsubMessage, SubscriberClient

    topic = "projects/my-project/topics/orders"
    subscription = "projects/my-project/subscriptions/worker"

    publisher = PublisherClient()
    subscriber = SubscriberClient()
    await publisher.create_topic(topic)
    await subscriber.create_subscription(subscription, topic)

    await publisher.publish(topic, [PubsubMessage(b'{"id": 1}', kind="order")])

    messages = await subscriber.pull(subscription, max_messages=10)
    assert messages[0].data == b'{"id": 1}'
    await subscriber.acknowledge(subscription, [messages[0].ack_id])

    await publisher.close()
    await subscriber.close()
```

## Run your actual code

Register a callback for a subscription and drongo pushes each published message
to it (returning acks; raising or `nack()` redelivers to the pullable backlog).
See [Executable handlers](../executable-handlers.md).

```python
from drongo import pubsub


@pubsub.subscription_handler("projects/p/subscriptions/worker")
def on_message(message):
    process(message.data)  # runs on publish
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete topic | Supported |
| Create / get / list / delete subscription | Supported |
| Publish (with attributes, fan-out to all subs) | Supported |
| Pull / acknowledge | Supported |
| Async client (`gcloud.aio.pubsub`, aiohttp/REST) | Supported |
| Executable handler (publish pushes to your callback) | Supported |
| Nack via `modify_ack_deadline(0)` (redelivery) | Supported |
| Streaming pull (`subscribe()`) | Planned |
| Ack-deadline expiry / retention | Planned |
| IAM, schemas, snapshots, seek | Planned |
