"""In-memory models for Google Cloud Pub/Sub.

Structured like moto's SQS/SNS backend: a plain in-memory state object with
clear domain methods. The gRPC emulator (``emulator.py``) is a thin adapter over
these methods, exactly as moto's ``responses.py`` is over ``SQSBackend``.

Analogy to moto's SQS:

* :class:`Topic` + :meth:`PubSubBackend.publish` (fan-out)  ~  SNS topic + publish
* :class:`Subscription` (its pullable backlog)             ~  SQS queue
* ``ack_id``                                               ~  SQS ``receipt_handle``
* :meth:`PubSubBackend.pull` / :meth:`acknowledge`         ~  receive / delete
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Message:
    """A published message sitting in a subscription's backlog."""

    data: bytes
    attributes: dict[str, str] = field(default_factory=dict)
    message_id: str = ""
    publish_time: datetime = field(default_factory=_now)
    ordering_key: str = ""


class PushMessage:
    """What a subscription handler receives (push-style delivery).

    Returning from the handler normally acknowledges the message; raising or
    calling :meth:`nack` returns it to the backlog so it can still be pulled.
    """

    def __init__(self, message: Message) -> None:
        self.data = message.data
        self.attributes = message.attributes
        self.message_id = message.message_id
        self.ordering_key = message.ordering_key
        self.publish_time = message.publish_time
        self._acked: bool | None = None

    def ack(self) -> None:
        self._acked = True

    def nack(self) -> None:
        self._acked = False


#: A subscription handler receives each delivered :class:`PushMessage`.
SubscriptionHandler = Callable[[PushMessage], Any]


@dataclass
class Topic:
    """A Pub/Sub topic. ``name`` is the full ``projects/P/topics/T`` path."""

    name: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Subscription:
    """A subscription: the pullable backlog for a topic (the SQS-queue analog)."""

    name: str
    topic: str
    ack_deadline_seconds: int = 10
    labels: dict[str, str] = field(default_factory=dict)
    #: Messages delivered by publish, not yet pulled.
    backlog: list[Message] = field(default_factory=list)
    #: Pulled-but-not-acked messages, keyed by ack id.
    outstanding: dict[str, Message] = field(default_factory=dict)


class PubSubBackend(BaseBackend):
    """In-memory Pub/Sub state.

    Topics and subscriptions are stored by full resource name, so publish can
    fan out across the whole namespace (like SNS calling into SQS in moto).
    """

    def setup(self) -> None:
        self.topics: dict[str, Topic] = {}
        self.subscriptions: dict[str, Subscription] = {}
        self.handlers: dict[str, SubscriptionHandler] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def register_handler(
        self, subscription_name: str, handler: SubscriptionHandler
    ) -> None:
        """Bind a callback to a subscription; publishes are pushed to it."""
        self.handlers[subscription_name] = handler

    def _deliver(self, subscription: Subscription, message: Message) -> None:
        """Push ``message`` to the subscription's handler, or enqueue it.

        With no handler the message lands in the pullable backlog (the existing
        pull model). With a handler it is delivered immediately; a normal return
        acks it, while a raise or ``nack()`` returns it to the backlog.
        """
        handler = self.handlers.get(subscription.name)
        if handler is None:
            subscription.backlog.append(message)
            return
        push = PushMessage(message)
        try:
            handler(push)
            acked = push._acked is not False
        except Exception:  # noqa: BLE001 - a failed push is a nack (redeliver)
            acked = False
        if not acked:
            subscription.backlog.append(message)

    # -- topics ------------------------------------------------------------

    def create_topic(self, name: str, *, labels: dict[str, str] | None = None) -> Topic:
        if name in self.topics:
            raise exceptions.already_exists(f"Topic already exists: {name}")
        topic = Topic(name=name, labels=dict(labels or {}))
        self.topics[name] = topic
        return topic

    def get_topic(self, name: str) -> Topic:
        try:
            return self.topics[name]
        except KeyError:
            raise exceptions.not_found(f"Topic not found: {name}")

    def list_topics(self, project: str) -> list[Topic]:
        prefix = f"{project}/topics/"
        return [self.topics[n] for n in sorted(self.topics) if n.startswith(prefix)]

    def delete_topic(self, name: str) -> None:
        self.get_topic(name)
        del self.topics[name]

    def publish(
        self, topic_name: str, messages: list[tuple[bytes, dict[str, str], str]]
    ) -> list[str]:
        """Publish messages, fanning out to every subscription on the topic."""
        self.get_topic(topic_name)
        ids: list[str] = []
        for data, attributes, ordering_key in messages:
            message_id = str(self._next())
            ids.append(message_id)
            for subscription in self.subscriptions.values():
                if subscription.topic == topic_name:
                    self._deliver(
                        subscription,
                        Message(
                            data=data,
                            attributes=dict(attributes),
                            message_id=message_id,
                            ordering_key=ordering_key,
                        ),
                    )
        return ids

    # -- subscriptions -----------------------------------------------------

    def create_subscription(
        self,
        name: str,
        topic: str,
        *,
        ack_deadline_seconds: int = 10,
        labels: dict[str, str] | None = None,
    ) -> Subscription:
        if name in self.subscriptions:
            raise exceptions.already_exists(f"Subscription already exists: {name}")
        self.get_topic(topic)  # 404 if the topic does not exist
        subscription = Subscription(
            name=name,
            topic=topic,
            ack_deadline_seconds=ack_deadline_seconds or 10,
            labels=dict(labels or {}),
        )
        self.subscriptions[name] = subscription
        return subscription

    def get_subscription(self, name: str) -> Subscription:
        try:
            return self.subscriptions[name]
        except KeyError:
            raise exceptions.not_found(f"Subscription not found: {name}")

    def list_subscriptions(self, project: str) -> list[Subscription]:
        prefix = f"{project}/subscriptions/"
        return [
            self.subscriptions[n]
            for n in sorted(self.subscriptions)
            if n.startswith(prefix)
        ]

    def delete_subscription(self, name: str) -> None:
        self.get_subscription(name)
        del self.subscriptions[name]

    # -- pull / ack --------------------------------------------------------

    def pull(self, name: str, max_messages: int) -> list[tuple[str, Message]]:
        """Deliver up to ``max_messages`` from the backlog, assigning ack ids."""
        subscription = self.get_subscription(name)
        limit = max_messages or 100
        delivered: list[tuple[str, Message]] = []
        while subscription.backlog and len(delivered) < limit:
            message = subscription.backlog.pop(0)
            ack_id = f"ack-{self._next()}"
            subscription.outstanding[ack_id] = message
            delivered.append((ack_id, message))
        return delivered

    def acknowledge(self, name: str, ack_ids: list[str]) -> None:
        subscription = self.get_subscription(name)
        for ack_id in ack_ids:
            subscription.outstanding.pop(ack_id, None)

    def modify_ack_deadline(
        self, name: str, ack_ids: list[str], ack_deadline_seconds: int
    ) -> None:
        """A deadline of 0 nacks the messages, returning them to the backlog."""
        subscription = self.get_subscription(name)
        if ack_deadline_seconds == 0:
            for ack_id in ack_ids:
                message = subscription.outstanding.pop(ack_id, None)
                if message is not None:
                    subscription.backlog.insert(0, message)


#: Project-keyed backends. Pub/Sub resources live in one shared namespace (keyed
#: by full name) so publish can fan out across projects; inspect via
#: ``get_backend("pubsub")[project]``.
pubsub_backends: BackendDict[PubSubBackend] = BackendDict(
    PubSubBackend, "pubsub", global_namespace=True
)
