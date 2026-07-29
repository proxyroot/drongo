"""Pub/Sub tests using the default (gRPC) client, served by drongo's emulator.

Note there is no ``transport="rest"`` anywhere: this is the plain client a user
writes in production, unchanged.
"""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "projects/test-project"
TOPIC = f"{PROJECT}/topics/events"
SUB = f"{PROJECT}/subscriptions/worker"


def _publisher():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def _subscriber():
    from google.cloud import pubsub_v1

    return pubsub_v1.SubscriberClient()


def test_create_and_get_topic() -> None:
    pub = _publisher()
    pub.create_topic(request={"name": TOPIC})
    assert pub.get_topic(request={"topic": TOPIC}).name == TOPIC


def test_duplicate_topic_conflicts() -> None:
    pub = _publisher()
    pub.create_topic(request={"name": TOPIC})
    with pytest.raises(gexc.AlreadyExists):
        pub.create_topic(request={"name": TOPIC})


def test_get_missing_topic_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _publisher().get_topic(request={"topic": TOPIC})


def test_list_topics() -> None:
    pub = _publisher()
    pub.create_topic(request={"name": TOPIC})
    pub.create_topic(request={"name": f"{PROJECT}/topics/other"})
    names = sorted(t.name for t in pub.list_topics(request={"project": PROJECT}))
    assert names == sorted([TOPIC, f"{PROJECT}/topics/other"])


def test_publish_pull_acknowledge() -> None:
    pub, sub = _publisher(), _subscriber()
    pub.create_topic(request={"name": TOPIC})
    sub.create_subscription(request={"name": SUB, "topic": TOPIC})

    pub.publish(TOPIC, b"hello", source="test").result(timeout=10)

    resp = sub.pull(request={"subscription": SUB, "max_messages": 10})
    assert len(resp.received_messages) == 1
    message = resp.received_messages[0].message
    assert message.data == b"hello"
    assert dict(message.attributes) == {"source": "test"}

    sub.acknowledge(
        request={
            "subscription": SUB,
            "ack_ids": [resp.received_messages[0].ack_id],
        }
    )
    again = sub.pull(
        request={"subscription": SUB, "max_messages": 10, "return_immediately": True}
    )
    assert len(again.received_messages) == 0


def test_publish_fans_out_to_all_subscriptions() -> None:
    pub, sub = _publisher(), _subscriber()
    pub.create_topic(request={"name": TOPIC})
    audit = f"{PROJECT}/subscriptions/audit"
    sub.create_subscription(request={"name": SUB, "topic": TOPIC})
    sub.create_subscription(request={"name": audit, "topic": TOPIC})

    pub.publish(TOPIC, b"event").result(timeout=10)

    for subscription in (SUB, audit):
        resp = sub.pull(request={"subscription": subscription, "max_messages": 10})
        assert len(resp.received_messages) == 1


def test_create_subscription_requires_existing_topic() -> None:
    with pytest.raises(gexc.NotFound):
        _subscriber().create_subscription(request={"name": SUB, "topic": TOPIC})


def test_nack_via_modify_ack_deadline_redelivers() -> None:
    pub, sub = _publisher(), _subscriber()
    pub.create_topic(request={"name": TOPIC})
    sub.create_subscription(request={"name": SUB, "topic": TOPIC})
    pub.publish(TOPIC, b"retry").result(timeout=10)

    resp = sub.pull(request={"subscription": SUB, "max_messages": 10})
    ack_id = resp.received_messages[0].ack_id
    sub.modify_ack_deadline(
        request={"subscription": SUB, "ack_ids": [ack_id], "ack_deadline_seconds": 0}
    )

    redelivered = sub.pull(
        request={"subscription": SUB, "max_messages": 10, "return_immediately": True}
    )
    assert len(redelivered.received_messages) == 1


def test_delete_topic_and_subscription() -> None:
    pub, sub = _publisher(), _subscriber()
    pub.create_topic(request={"name": TOPIC})
    sub.create_subscription(request={"name": SUB, "topic": TOPIC})

    sub.delete_subscription(request={"subscription": SUB})
    pub.delete_topic(request={"topic": TOPIC})

    with pytest.raises(gexc.NotFound):
        pub.get_topic(request={"topic": TOPIC})


def test_backend_is_inspectable(drongo) -> None:
    pub = _publisher()
    pub.create_topic(request={"name": TOPIC})
    assert TOPIC in drongo.backend("pubsub").topics
