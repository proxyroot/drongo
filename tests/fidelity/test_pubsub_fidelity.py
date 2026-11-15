"""Pub/Sub fidelity scenarios.

Delivery is the part of Pub/Sub that is easy to fake wrongly, so these cover
ack/nack, redelivery, fan-out, ordering keys and the error mapping, rather than
CRUD on topics.

Two bits of plumbing keep the same body honest on both targets:

* :func:`pull_messages` retries the pull. A single synchronous pull against real
  Pub/Sub is allowed to come back empty even when the backlog is not, so one
  pull would be flaky live while being conclusive under the mock.
* :func:`let_ack_deadline_expire` waits out a real deadline. The mock has no
  wall clock to advance, so there is nothing to wait for there.

Neither changes an assertion, and no test branches on which target is active.
"""

from __future__ import annotations

import time

import pytest
from google.api_core import exceptions as gexc

from . import gcp_verified, known_gap, live_requests_allowed

#: The shortest ack deadline real Pub/Sub accepts.
MIN_ACK_DEADLINE_SECONDS = 10


def pull_messages(subscriber, subscription: str, *, expected: int, attempts: int = 5):
    """Pull until ``expected`` messages have arrived, or ``attempts`` run out.

    With ``expected=0`` every attempt runs and the result should stay empty,
    which is how "nothing more is delivered" is asserted.
    """
    collected: list = []
    for _ in range(attempts):
        response = subscriber.pull(
            request={
                "subscription": subscription,
                "max_messages": 10,
                "return_immediately": True,
            }
        )
        collected.extend(response.received_messages)
        if expected and len(collected) >= expected:
            break
    return collected


def let_ack_deadline_expire(seconds: int = MIN_ACK_DEADLINE_SECONDS) -> None:
    """Wait for an outstanding message's ack deadline to lapse."""
    if live_requests_allowed():
        time.sleep(seconds + 5)


def ack(subscriber, subscription: str, *received) -> None:
    subscriber.acknowledge(
        request={
            "subscription": subscription,
            "ack_ids": [message.ack_id for message in received],
        }
    )


# -- delivery ---------------------------------------------------------------


@gcp_verified
def test_published_message_is_pullable_with_its_attributes(
    publisher, subscriber, topic, subscription
) -> None:
    publisher.publish(topic, b"hello", source="fidelity").result(timeout=30)

    received = pull_messages(subscriber, subscription, expected=1)

    assert len(received) == 1
    assert received[0].message.data == b"hello"
    assert dict(received[0].message.attributes) == {"source": "fidelity"}


@gcp_verified
def test_acked_message_is_not_redelivered(
    publisher, subscriber, topic, subscription
) -> None:
    publisher.publish(topic, b"once").result(timeout=30)
    received = pull_messages(subscriber, subscription, expected=1)

    ack(subscriber, subscription, *received)

    assert pull_messages(subscriber, subscription, expected=0) == []


@gcp_verified
def test_nack_redelivers_the_message(
    publisher, subscriber, topic, subscription
) -> None:
    """A zero ack deadline returns the message to the backlog immediately."""
    publisher.publish(topic, b"retry").result(timeout=30)
    received = pull_messages(subscriber, subscription, expected=1)

    subscriber.modify_ack_deadline(
        request={
            "subscription": subscription,
            "ack_ids": [received[0].ack_id],
            "ack_deadline_seconds": 0,
        }
    )

    redelivered = pull_messages(subscriber, subscription, expected=1)
    assert len(redelivered) == 1
    assert redelivered[0].message.data == b"retry"


@gcp_verified
@known_gap(
    "drongo holds pulled messages indefinitely: an ack deadline that lapses "
    "without an ack does not return the message to the backlog"
)
def test_expired_ack_deadline_redelivers_the_message(
    publisher, subscriber, topic, subscription_factory
) -> None:
    """Pulling without acking is not an ack: the message must come back."""
    subscription = subscription_factory(
        topic, ack_deadline_seconds=MIN_ACK_DEADLINE_SECONDS
    )
    publisher.publish(topic, b"unacked").result(timeout=30)
    assert len(pull_messages(subscriber, subscription, expected=1)) == 1

    let_ack_deadline_expire()

    redelivered = pull_messages(subscriber, subscription, expected=1)
    assert len(redelivered) == 1
    assert redelivered[0].message.data == b"unacked"


@gcp_verified
def test_publish_fans_out_to_every_subscription(
    publisher, subscriber, topic, subscription_factory
) -> None:
    """Each subscription gets its own copy, so one acking does not consume it."""
    workers = subscription_factory(topic, "workers")
    audit = subscription_factory(topic, "audit")

    publisher.publish(topic, b"event").result(timeout=30)

    for subscription in (workers, audit):
        received = pull_messages(subscriber, subscription, expected=1)
        assert [m.message.data for m in received] == [b"event"]


@gcp_verified
def test_max_messages_is_an_upper_bound(
    publisher, subscriber, topic, subscription
) -> None:
    """``max_messages`` caps a pull; it does not promise that many."""
    for index in range(3):
        publisher.publish(topic, f"m{index}".encode()).result(timeout=30)

    response = subscriber.pull(
        request={
            "subscription": subscription,
            "max_messages": 2,
            "return_immediately": True,
        }
    )

    assert len(response.received_messages) <= 2


@gcp_verified
def test_publish_returns_distinct_message_ids(publisher, topic) -> None:
    first = publisher.publish(topic, b"a").result(timeout=30)
    second = publisher.publish(topic, b"b").result(timeout=30)

    assert first and second
    assert first != second


@gcp_verified
def test_ordering_key_is_preserved_and_ordered(
    subscriber, topic, subscription_factory, gcp_target
) -> None:
    """Same-key messages arrive in publish order, with the key echoed back."""
    from google.cloud import pubsub_v1

    ordered_publisher = pubsub_v1.PublisherClient(
        publisher_options=pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
    )
    subscription = subscription_factory(topic, "ordered", enable_message_ordering=True)

    for index in range(3):
        ordered_publisher.publish(
            topic, f"m{index}".encode(), ordering_key="tenant-a"
        ).result(timeout=30)

    received = pull_messages(subscriber, subscription, expected=3)

    assert [m.message.data for m in received] == [b"m0", b"m1", b"m2"]
    assert {m.message.ordering_key for m in received} == {"tenant-a"}


# -- error semantics --------------------------------------------------------


@gcp_verified
def test_publish_to_missing_topic_is_not_found(publisher, gcp_target) -> None:
    absent = gcp_target.topic_path("never-created")

    with pytest.raises(gexc.NotFound):
        publisher.publish(absent, b"payload").result(timeout=30)


@gcp_verified
def test_get_missing_topic_is_not_found(publisher, gcp_target) -> None:
    with pytest.raises(gexc.NotFound):
        publisher.get_topic(request={"topic": gcp_target.topic_path("absent")})


@gcp_verified
def test_duplicate_topic_already_exists(publisher, topic) -> None:
    with pytest.raises(gexc.AlreadyExists):
        publisher.create_topic(request={"name": topic})


@gcp_verified
def test_subscription_on_missing_topic_is_not_found(subscriber, gcp_target) -> None:
    with pytest.raises(gexc.NotFound):
        subscriber.create_subscription(
            request={
                "name": gcp_target.subscription_path("orphan"),
                "topic": gcp_target.topic_path("never-created"),
            }
        )


@gcp_verified
def test_duplicate_subscription_already_exists(subscriber, topic, subscription) -> None:
    with pytest.raises(gexc.AlreadyExists):
        subscriber.create_subscription(request={"name": subscription, "topic": topic})


@gcp_verified
def test_pull_from_deleted_subscription_is_not_found(subscriber, subscription) -> None:
    subscriber.delete_subscription(request={"subscription": subscription})

    with pytest.raises(gexc.NotFound):
        subscriber.pull(
            request={
                "subscription": subscription,
                "max_messages": 1,
                "return_immediately": True,
            }
        )


# -- resource state ---------------------------------------------------------


@gcp_verified
def test_subscription_reports_its_topic_and_ack_deadline(
    subscriber, topic, subscription_factory
) -> None:
    subscription = subscription_factory(topic, "configured", ack_deadline_seconds=30)

    fetched = subscriber.get_subscription(request={"subscription": subscription})

    assert fetched.topic == topic
    assert fetched.ack_deadline_seconds == 30


@gcp_verified
def test_created_topic_appears_in_the_project_listing(
    publisher, topic, gcp_target
) -> None:
    """Asserts membership: a real project holds topics this run did not create."""
    listed = publisher.list_topics(
        request={"project": f"projects/{gcp_target.project}"}
    )

    assert topic in [found.name for found in listed]
