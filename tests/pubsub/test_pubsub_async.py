"""Async Pub/Sub tests using the real gcloud.aio.pubsub client (aiohttp/REST).

These exercise the aiohttp interceptor and the Pub/Sub REST layer. They are
skipped when gcloud-aio-pubsub / aiohttp are not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("gcloud.aio.pubsub")
pytest.importorskip("aiohttp")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
TOPIC = f"projects/{PROJECT}/topics/orders"
SUB = f"projects/{PROJECT}/subscriptions/worker"


async def test_create_publish_pull_ack() -> None:
    from gcloud.aio.pubsub import PublisherClient, PubsubMessage, SubscriberClient

    publisher = PublisherClient()
    subscriber = SubscriberClient()
    try:
        await publisher.create_topic(TOPIC)
        await subscriber.create_subscription(SUB, TOPIC)

        ids = await publisher.publish(
            TOPIC, [PubsubMessage(b"hello", tag="a"), PubsubMessage(b"world")]
        )
        assert ids["messageIds"] == ["1", "2"]

        messages = await subscriber.pull(SUB, max_messages=10)
        assert [m.data for m in messages] == [b"hello", b"world"]
        assert messages[0].attributes == {"tag": "a"}

        await subscriber.acknowledge(SUB, [m.ack_id for m in messages])
        assert await subscriber.pull(SUB, max_messages=10) == []
    finally:
        await publisher.close()
        await subscriber.close()


async def test_nack_via_modify_ack_deadline_redelivers() -> None:
    from gcloud.aio.pubsub import PublisherClient, PubsubMessage, SubscriberClient

    publisher = PublisherClient()
    subscriber = SubscriberClient()
    try:
        await publisher.create_topic(TOPIC)
        await subscriber.create_subscription(SUB, TOPIC)
        await publisher.publish(TOPIC, [PubsubMessage(b"retry-me")])

        (message,) = await subscriber.pull(SUB, max_messages=10)
        # Deadline 0 nacks: the message returns to the backlog.
        await subscriber.modify_ack_deadline(SUB, [message.ack_id], 0)

        (again,) = await subscriber.pull(SUB, max_messages=10)
        assert again.data == b"retry-me"
    finally:
        await publisher.close()
        await subscriber.close()


async def test_list_and_delete_topic() -> None:
    from gcloud.aio.pubsub import PublisherClient

    publisher = PublisherClient()
    try:
        await publisher.create_topic(TOPIC)
        listed = await publisher.list_topics(f"projects/{PROJECT}")
        assert [t["name"] for t in listed["topics"]] == [TOPIC]

        await publisher.delete_topic(TOPIC)
        assert await publisher.list_topics(f"projects/{PROJECT}") == {"topics": []}
    finally:
        await publisher.close()


async def test_pull_missing_subscription_raises() -> None:
    import aiohttp
    from gcloud.aio.pubsub import SubscriberClient

    subscriber = SubscriberClient()
    try:
        with pytest.raises(aiohttp.ClientResponseError) as exc:
            await subscriber.pull(SUB, max_messages=1)
        assert exc.value.status == 404
    finally:
        await subscriber.close()


async def test_async_publish_visible_to_sync_grpc_pull() -> None:
    """State is shared: a message published over REST is pullable over gRPC."""
    grpc = pytest.importorskip("google.cloud.pubsub_v1")
    from gcloud.aio.pubsub import PublisherClient, PubsubMessage

    sync_publisher = grpc.PublisherClient()
    sync_subscriber = grpc.SubscriberClient()
    sync_publisher.create_topic(name=TOPIC)
    sync_subscriber.create_subscription(name=SUB, topic=TOPIC)

    async_publisher = PublisherClient()
    try:
        await async_publisher.publish(TOPIC, [PubsubMessage(b"from-async", via="aio")])
    finally:
        await async_publisher.close()

    pulled = sync_subscriber.pull(subscription=SUB, max_messages=10)
    assert [rm.message.data for rm in pulled.received_messages] == [b"from-async"]
    assert dict(pulled.received_messages[0].message.attributes) == {"via": "aio"}
