"""Google Cloud Pub/Sub mock.

Registers the ``pubsub`` service with the drongo engine on import. Pub/Sub is
gRPC-first, so it is served by an in-process gRPC :class:`PubSubEmulator` (via
``PUBSUB_EMULATOR_HOST``) rather than the HTTP interception layer.
"""

from __future__ import annotations

from collections.abc import Callable

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.pubsub.emulator import PubSubEmulator
from drongo.services.pubsub.models import (
    PubSubBackend,
    SubscriptionHandler,
    pubsub_backends,
)

__all__ = [
    "PubSubBackend",
    "PubSubEmulator",
    "pubsub_backends",
    "register_subscription_handler",
    "subscription_handler",
]


def _project(subscription_name: str) -> str:
    parts = subscription_name.split("/")
    if len(parts) < 4 or parts[0] != "projects" or parts[2] != "subscriptions":
        raise ValueError(
            "Expected a subscription resource name like "
            "'projects/<p>/subscriptions/<s>', got: " + repr(subscription_name)
        )
    return parts[1]


def register_subscription_handler(
    subscription_name: str, handler: SubscriptionHandler
) -> None:
    """Bind a callback to a subscription; published messages are pushed to it.

    The handler receives a
    :class:`~drongo.services.pubsub.models.PushMessage`. A normal return acks the
    message; raising or calling ``nack()`` returns it to the pullable backlog.
    """
    pubsub_backends[_project(subscription_name)].register_handler(
        subscription_name, handler
    )


def subscription_handler(
    subscription_name: str,
) -> Callable[[SubscriptionHandler], SubscriptionHandler]:
    """Decorator form of :func:`register_subscription_handler`.

    ::

        @pubsub.subscription_handler("projects/p/subscriptions/worker")
        def on_message(message):
            process(message.data)   # returning acks; raising redelivers
    """

    def decorator(handler: SubscriptionHandler) -> SubscriptionHandler:
        register_subscription_handler(subscription_name, handler)
        return handler

    return decorator


register_service(
    ServiceDefinition(
        name="pubsub",
        backends=pubsub_backends,
        emulator=PubSubEmulator(pubsub_backends),
    )
)
