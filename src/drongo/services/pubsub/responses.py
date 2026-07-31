"""HTTP handlers for the Pub/Sub REST (v1) API.

Pub/Sub's sync client is gRPC-only and is served by the in-process gRPC emulator
(``emulator.py``). The async client (``gcloud.aio.pubsub``) is aiohttp/REST, so it
needs an HTTP surface. Both are thin adapters over the same
:class:`~drongo.services.pubsub.models.PubSubBackend`, so a message published
through the REST layer can be pulled through the gRPC one and vice versa.

Wire format follows the REST docs: message ``data`` is base64, and pulled
messages carry an ``ackId``, ``messageId`` and RFC3339 ``publishTime``.
"""

from __future__ import annotations

import base64
from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.pubsub.models import (
    Message,
    PubSubBackend,
    Subscription,
    Topic,
    pubsub_backends,
)


def _project_of(resource: str) -> str:
    """The project id from ``projects/<p>/...`` (or a bare ``projects/<p>``)."""
    parts = resource.split("/")
    return parts[1] if len(parts) > 1 else resource


def _publish_time(message: Message) -> str:
    return message.publish_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class PubSubResponse(BaseResponse):
    """Handles Pub/Sub REST requests against the shared in-memory backend."""

    def _backend(self, resource: str) -> PubSubBackend:
        return pubsub_backends[_project_of(resource)]

    # -- topics ------------------------------------------------------------

    def create_topic(self, request: Request) -> HttpResponse:
        name = request.path_params["topic"]
        body = request.json()
        topic = self._backend(name).create_topic(name, labels=body.get("labels"))
        return json_response(_topic_resource(topic))

    def get_topic(self, request: Request) -> HttpResponse:
        name = request.path_params["topic"]
        return json_response(_topic_resource(self._backend(name).get_topic(name)))

    def list_topics(self, request: Request) -> HttpResponse:
        project = request.path_params["project"]
        topics = self._backend(project).list_topics(project)
        return json_response({"topics": [_topic_resource(t) for t in topics]})

    def delete_topic(self, request: Request) -> HttpResponse:
        name = request.path_params["topic"]
        self._backend(name).delete_topic(name)
        return json_response({})

    def publish(self, request: Request) -> HttpResponse:
        name = request.path_params["topic"]
        body = request.json()
        messages = [
            (
                base64.b64decode(m.get("data", "") or ""),
                dict(m.get("attributes") or {}),
                m.get("orderingKey", ""),
            )
            for m in body.get("messages", [])
        ]
        ids = self._backend(name).publish(name, messages)
        return json_response({"messageIds": ids})

    # -- subscriptions -----------------------------------------------------

    def create_subscription(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        body = request.json()
        subscription = self._backend(name).create_subscription(
            name,
            body.get("topic", ""),
            ack_deadline_seconds=body.get("ackDeadlineSeconds", 10),
            labels=body.get("labels"),
        )
        return json_response(_subscription_resource(subscription))

    def get_subscription(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        subscription = self._backend(name).get_subscription(name)
        return json_response(_subscription_resource(subscription))

    def list_subscriptions(self, request: Request) -> HttpResponse:
        project = request.path_params["project"]
        subscriptions = self._backend(project).list_subscriptions(project)
        return json_response(
            {"subscriptions": [_subscription_resource(s) for s in subscriptions]}
        )

    def delete_subscription(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        self._backend(name).delete_subscription(name)
        return json_response({})

    # -- pull / ack --------------------------------------------------------

    def pull(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        body = request.json()
        delivered = self._backend(name).pull(name, body.get("maxMessages", 0))
        return json_response(
            {
                "receivedMessages": [
                    {"ackId": ack_id, "message": _message_resource(message)}
                    for ack_id, message in delivered
                ]
            }
        )

    def acknowledge(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        self._backend(name).acknowledge(name, request.json().get("ackIds", []))
        return json_response({})

    def modify_ack_deadline(self, request: Request) -> HttpResponse:
        name = request.path_params["subscription"]
        body = request.json()
        self._backend(name).modify_ack_deadline(
            name, body.get("ackIds", []), body.get("ackDeadlineSeconds", 0)
        )
        return json_response({})


def _topic_resource(topic: Topic) -> dict[str, Any]:
    resource: dict[str, Any] = {"name": topic.name}
    if topic.labels:
        resource["labels"] = dict(topic.labels)
    return resource


def _subscription_resource(subscription: Subscription) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "name": subscription.name,
        "topic": subscription.topic,
        "ackDeadlineSeconds": subscription.ack_deadline_seconds,
    }
    if subscription.labels:
        resource["labels"] = dict(subscription.labels)
    return resource


def _message_resource(message: Message) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "messageId": message.message_id,
        "publishTime": _publish_time(message),
    }
    if message.data:
        resource["data"] = base64.b64encode(message.data).decode("ascii")
    if message.attributes:
        resource["attributes"] = dict(message.attributes)
    if message.ordering_key:
        resource["orderingKey"] = message.ordering_key
    return resource
