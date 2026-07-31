"""URL routing table for the Pub/Sub REST (v1) API.

Served to aiohttp-based async clients (``gcloud.aio.pubsub``) via the aiohttp
interceptor. The sync gRPC client is handled by the emulator instead.
"""

from __future__ import annotations

from drongo.services.pubsub.responses import PubSubResponse

_TOPIC = r"/v1/(?P<topic>projects/[^/]+/topics/[^/:]+)"
_SUB = r"/v1/(?P<subscription>projects/[^/]+/subscriptions/[^/:]+)"
_PROJECT = r"/v1/(?P<project>projects/[^/]+)"

# Used only to register with the requests-based `responses` mock. The aiohttp
# interceptor that actually serves the async client routes by path with its own
# host gate, so the dynamic emulator host does not need to appear here.
url_bases = [r"https?://pubsub\.googleapis\.com"]

url_paths = {
    # Topic actions (specific suffixes first).
    f"POST {_TOPIC}:publish": PubSubResponse.publish,
    f"POST {_SUB}:pull": PubSubResponse.pull,
    f"POST {_SUB}:acknowledge": PubSubResponse.acknowledge,
    f"POST {_SUB}:modifyAckDeadline": PubSubResponse.modify_ack_deadline,
    # Collections.
    f"GET {_PROJECT}/topics": PubSubResponse.list_topics,
    f"GET {_PROJECT}/subscriptions": PubSubResponse.list_subscriptions,
    # Topics.
    f"PUT {_TOPIC}": PubSubResponse.create_topic,
    f"GET {_TOPIC}": PubSubResponse.get_topic,
    f"DELETE {_TOPIC}": PubSubResponse.delete_topic,
    # Subscriptions.
    f"PUT {_SUB}": PubSubResponse.create_subscription,
    f"GET {_SUB}": PubSubResponse.get_subscription,
    f"DELETE {_SUB}": PubSubResponse.delete_subscription,
}
