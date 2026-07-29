"""Pub/Sub executable handlers: publish pushes messages to a real callback."""

from __future__ import annotations

import pytest

from drongo import get_backend, pubsub

pytestmark = pytest.mark.usefixtures("drongo")

TOPIC = "projects/test-project/topics/orders"
SUB = "projects/test-project/subscriptions/worker"


def _clients():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient(), pubsub_v1.SubscriberClient()


def _setup(publisher, subscriber) -> None:
    publisher.create_topic(request={"name": TOPIC})
    subscriber.create_subscription(request={"name": SUB, "topic": TOPIC})


def test_publish_pushes_to_handler() -> None:
    publisher, subscriber = _clients()
    _setup(publisher, subscriber)
    received = []

    @pubsub.subscription_handler(SUB)
    def on_message(message) -> None:
        received.append((message.data, dict(message.attributes)))

    publisher.publish(TOPIC, b'{"id": 1}', kind="order").result()

    assert received == [(b'{"id": 1}', {"kind": "order"})]
    # Acked (normal return) => nothing left to pull.
    pulled = subscriber.pull(request={"subscription": SUB, "max_messages": 10})
    assert list(pulled.received_messages) == []


def test_handler_raise_redelivers_to_backlog() -> None:
    publisher, subscriber = _clients()
    _setup(publisher, subscriber)

    @pubsub.subscription_handler(SUB)
    def on_message(message) -> None:
        raise RuntimeError("processing failed")

    publisher.publish(TOPIC, b"retry-me").result()

    # Failed push is a nack: the message is still pullable.
    pulled = subscriber.pull(request={"subscription": SUB, "max_messages": 10})
    assert pulled.received_messages[0].message.data == b"retry-me"


def test_nack_returns_message_to_backlog() -> None:
    publisher, subscriber = _clients()
    _setup(publisher, subscriber)

    @pubsub.subscription_handler(SUB)
    def on_message(message) -> None:
        message.nack()

    publisher.publish(TOPIC, b"later").result()
    pulled = subscriber.pull(request={"subscription": SUB, "max_messages": 10})
    assert pulled.received_messages[0].message.data == b"later"


def test_no_handler_uses_pull_model() -> None:
    publisher, subscriber = _clients()
    _setup(publisher, subscriber)
    publisher.publish(TOPIC, b"pull-me").result()

    pulled = subscriber.pull(request={"subscription": SUB, "max_messages": 10})
    assert pulled.received_messages[0].message.data == b"pull-me"


def test_register_via_backend_method() -> None:
    publisher, subscriber = _clients()
    _setup(publisher, subscriber)
    got = []
    get_backend("pubsub")["test-project"].register_handler(
        SUB, lambda m: got.append(m.data)
    )

    publisher.publish(TOPIC, b"via-backend").result()
    assert got == [b"via-backend"]
