"""In-process gRPC emulator for Pub/Sub.

Runs a real gRPC server backed by :class:`PubSubBackend` and points the client at
it via ``PUBSUB_EMULATOR_HOST``, so the user's normal (default gRPC) client works
with no code change. The handlers are thin adapters over the backend, exactly
like moto's ``responses.py`` handlers over ``SQSBackend``.

We build the server with generic gRPC handlers using the client library's own
proto-plus (de)serializers, so no generated servicer classes are required. The
required libraries (``grpcio`` plus the pubsub proto types) ship with
``google-cloud-pubsub``; if they are absent, :meth:`start` no-ops.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError
from drongo.services.pubsub.models import PubSubBackend, pubsub_backends

_GLOBAL = "_global_"


class PubSubEmulator(BaseEmulator):
    """Serves the Pub/Sub gRPC API from an in-process server."""

    ENV_VAR = "PUBSUB_EMULATOR_HOST"

    def __init__(self, backends: Any = pubsub_backends) -> None:
        self._backends = backends
        # The gRPC server is created once and reused across scopes (backend
        # state is reset between scopes by the controller, and the server reads
        # it live). Per-scope cost is then just swapping the env var.
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._prev_host: str | None = None
        self._grpc: Any = None
        self._pt: Any = None
        self._empty: Any = None

    def _backend(self) -> PubSubBackend:
        return self._backends[_GLOBAL]

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._available is False:
            return  # grpcio / google-cloud-pubsub unavailable: nothing to emulate
        if self._server is None and not self._boot():
            self._available = False
            return
        self._available = True
        self._prev_host = os.environ.get(self.ENV_VAR)
        os.environ[self.ENV_VAR] = f"localhost:{self._port}"

    def stop(self) -> None:
        if self._server is None:
            return  # never started (unavailable): leave the environment alone
        if self._prev_host is None:
            os.environ.pop(self.ENV_VAR, None)
        else:
            os.environ[self.ENV_VAR] = self._prev_host
        self._prev_host = None

    def _boot(self) -> bool:
        try:
            import grpc
            from google.protobuf import empty_pb2
            from google.pubsub_v1 import types as pt
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._pt, self._empty = grpc, pt, empty_pb2
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, pt, empty = self._grpc, self._pt, self._empty

        status = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
            412: grpc.StatusCode.FAILED_PRECONDITION,
        }

        def guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(request: Any, context: Any) -> Any:
                try:
                    return fn(request, context)
                except DrongoHttpError as exc:
                    context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return wrapped

        def unary(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            ser = getattr(resp_t, "serialize", None) or resp_t.SerializeToString
            de = getattr(req_t, "deserialize", None) or req_t.FromString
            return grpc.unary_unary_rpc_method_handler(
                guard(fn), request_deserializer=de, response_serializer=ser
            )

        publisher = {
            "CreateTopic": unary(pt.Topic, pt.Topic, self._create_topic),
            "GetTopic": unary(pt.GetTopicRequest, pt.Topic, self._get_topic),
            "ListTopics": unary(
                pt.ListTopicsRequest, pt.ListTopicsResponse, self._list_topics
            ),
            "DeleteTopic": unary(
                pt.DeleteTopicRequest, empty.Empty, self._delete_topic
            ),
            "Publish": unary(pt.PublishRequest, pt.PublishResponse, self._publish),
        }
        subscriber = {
            "CreateSubscription": unary(
                pt.Subscription, pt.Subscription, self._create_subscription
            ),
            "GetSubscription": unary(
                pt.GetSubscriptionRequest, pt.Subscription, self._get_subscription
            ),
            "ListSubscriptions": unary(
                pt.ListSubscriptionsRequest,
                pt.ListSubscriptionsResponse,
                self._list_subscriptions,
            ),
            "DeleteSubscription": unary(
                pt.DeleteSubscriptionRequest, empty.Empty, self._delete_subscription
            ),
            "Pull": unary(pt.PullRequest, pt.PullResponse, self._pull),
            "Acknowledge": unary(pt.AcknowledgeRequest, empty.Empty, self._acknowledge),
            "ModifyAckDeadline": unary(
                pt.ModifyAckDeadlineRequest, empty.Empty, self._modify_ack_deadline
            ),
        }
        return (
            grpc.method_handlers_generic_handler(
                "google.pubsub.v1.Publisher", publisher
            ),
            grpc.method_handlers_generic_handler(
                "google.pubsub.v1.Subscriber", subscriber
            ),
        )

    # -- topic handlers ----------------------------------------------------

    def _create_topic(self, request: Any, context: Any) -> Any:
        topic = self._backend().create_topic(request.name, labels=dict(request.labels))
        return self._pt.Topic(name=topic.name, labels=topic.labels)

    def _get_topic(self, request: Any, context: Any) -> Any:
        topic = self._backend().get_topic(request.topic)
        return self._pt.Topic(name=topic.name, labels=topic.labels)

    def _list_topics(self, request: Any, context: Any) -> Any:
        topics = self._backend().list_topics(request.project)
        return self._pt.ListTopicsResponse(
            topics=[self._pt.Topic(name=t.name, labels=t.labels) for t in topics]
        )

    def _delete_topic(self, request: Any, context: Any) -> Any:
        self._backend().delete_topic(request.topic)
        return self._empty.Empty()

    def _publish(self, request: Any, context: Any) -> Any:
        messages = [
            (m.data, dict(m.attributes), m.ordering_key) for m in request.messages
        ]
        ids = self._backend().publish(request.topic, messages)
        return self._pt.PublishResponse(message_ids=ids)

    # -- subscription handlers ---------------------------------------------

    def _create_subscription(self, request: Any, context: Any) -> Any:
        subscription = self._backend().create_subscription(
            request.name,
            request.topic,
            ack_deadline_seconds=request.ack_deadline_seconds,
            labels=dict(request.labels),
        )
        return self._to_subscription_proto(subscription)

    def _get_subscription(self, request: Any, context: Any) -> Any:
        subscription = self._backend().get_subscription(request.subscription)
        return self._to_subscription_proto(subscription)

    def _list_subscriptions(self, request: Any, context: Any) -> Any:
        subscriptions = self._backend().list_subscriptions(request.project)
        return self._pt.ListSubscriptionsResponse(
            subscriptions=[self._to_subscription_proto(s) for s in subscriptions]
        )

    def _delete_subscription(self, request: Any, context: Any) -> Any:
        self._backend().delete_subscription(request.subscription)
        return self._empty.Empty()

    def _pull(self, request: Any, context: Any) -> Any:
        delivered = self._backend().pull(request.subscription, request.max_messages)
        received = [
            self._pt.ReceivedMessage(
                ack_id=ack_id, message=self._to_message_proto(message)
            )
            for ack_id, message in delivered
        ]
        return self._pt.PullResponse(received_messages=received)

    def _acknowledge(self, request: Any, context: Any) -> Any:
        self._backend().acknowledge(request.subscription, list(request.ack_ids))
        return self._empty.Empty()

    def _modify_ack_deadline(self, request: Any, context: Any) -> Any:
        self._backend().modify_ack_deadline(
            request.subscription,
            list(request.ack_ids),
            request.ack_deadline_seconds,
        )
        return self._empty.Empty()

    # -- converters --------------------------------------------------------

    def _to_subscription_proto(self, subscription: Any) -> Any:
        return self._pt.Subscription(
            name=subscription.name,
            topic=subscription.topic,
            ack_deadline_seconds=subscription.ack_deadline_seconds,
            labels=subscription.labels,
        )

    def _to_message_proto(self, message: Any) -> Any:
        return self._pt.PubsubMessage(
            data=message.data,
            attributes=message.attributes,
            message_id=message.message_id,
            publish_time=message.publish_time,
            ordering_key=message.ordering_key,
        )
