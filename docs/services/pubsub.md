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
            request={"subscription": f"projects/p/subscriptions/{sub}", "max_messages": 10}
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

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete topic | Supported |
| Create / get / list / delete subscription | Supported |
| Publish (with attributes, fan-out to all subs) | Supported |
| Pull / acknowledge | Supported |
| Nack via `modify_ack_deadline(0)` (redelivery) | Supported |
| Streaming pull (`subscribe()`) | Planned |
| Ack-deadline expiry / retention | Planned |
| IAM, schemas, snapshots, seek | Planned |
