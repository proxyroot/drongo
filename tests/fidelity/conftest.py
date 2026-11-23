"""Fixtures for the dual-target fidelity suite.

Everything here is written so a scenario body reads the same against the mock
and against real GCP. The target-specific parts live in :func:`gcp_target`:
under the mock it activates ``mock_gcp``, and live it hands back the project
from ``DRONGO_TEST_PROJECT``.

Live runs create real resources, so every fixture that creates one:

1. names it ``drongo-fid-<run id>-<slug>`` (buckets share a global namespace,
   so names have to be unique per run, not just per project);
2. labels it ``drongo-fidelity=<run id>``;
3. registers a deleter with the :class:`Ledger`, which tears down in reverse
   order (subscription before topic, blobs before bucket).

A crashed run cannot register anything, so a session-end sweep also deletes
leftovers carrying the label. Both are no-ops under the mock, where state is
discarded with the backend.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

from drongo.core.credentials import DEFAULT_PROJECT
from drongo.core.decorator import mock_gcp

from . import (
    ALLOW_LIVE_ENV,
    FIDELITY_LABEL,
    FIDELITY_PREFIX,
    PROJECT_ENV,
    live_project,
    live_requests_allowed,
)


@dataclass(frozen=True)
class Target:
    """Where the scenario currently under test is pointed."""

    project: str
    is_live: bool
    run_id: str

    def name(self, slug: str) -> str:
        """A run-unique resource name for ``slug``."""
        return f"{FIDELITY_PREFIX}-{self.run_id}-{slug}"

    @property
    def labels(self) -> dict[str, str]:
        """The label every resource this run creates is stamped with."""
        return {FIDELITY_LABEL: self.run_id}

    def topic_path(self, slug: str) -> str:
        return f"projects/{self.project}/topics/{self.name(slug)}"

    def subscription_path(self, slug: str) -> str:
        return f"projects/{self.project}/subscriptions/{self.name(slug)}"


class Ledger:
    """Deleters for the resources a test created, torn down in reverse."""

    def __init__(self) -> None:
        self._deleters: list[tuple[str, Callable[[], None]]] = []

    def add(self, what: str, delete: Callable[[], None]) -> None:
        self._deleters.append((what, delete))

    def drain(self) -> list[str]:
        """Run every deleter, newest first. Returns what could not be deleted.

        A failure to clean up must not fail the test that already passed, but it
        does need to be visible, so the names come back for the caller to warn
        about.
        """
        failed: list[str] = []
        while self._deleters:
            what, delete = self._deleters.pop()
            try:
                delete()
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                failed.append(f"{what}: {exc}")
        return failed


@pytest.fixture(scope="session")
def fidelity_run_id() -> str:
    """Short id shared by every resource created in this test session."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
def gcp_target(fidelity_run_id: str) -> Iterator[Target]:
    """Point the test at the mock (default) or at real GCP.

    This is the only fixture that knows which target is active, which is what
    keeps the scenario bodies identical between the two.
    """
    if live_requests_allowed():
        yield Target(project=live_project(), is_live=True, run_id=fidelity_run_id)
        return
    with mock_gcp():
        yield Target(project=DEFAULT_PROJECT, is_live=False, run_id=fidelity_run_id)


@pytest.fixture
def ledger(gcp_target: Target) -> Iterator[Ledger]:
    """Per-test cleanup registry. Drains after the test, pass or fail."""
    entries = Ledger()
    yield entries
    failed = entries.drain()
    if failed and gcp_target.is_live:
        pytest.fail(
            "fidelity cleanup left resources behind, delete them by hand:\n  "
            + "\n  ".join(failed),
            pytrace=False,
        )


# -- Cloud Storage ----------------------------------------------------------


@pytest.fixture
def storage_client(gcp_target: Target):
    """A Cloud Storage client bound to the active target.

    Overrides the client in the top-level conftest: this one is constructed
    inside the mock scope and uses the live project when live.
    """
    from google.cloud import storage

    return storage.Client(project=gcp_target.project)


@pytest.fixture
def bucket_factory(storage_client, gcp_target: Target, ledger: Ledger):
    """Create labelled, run-uniquely named buckets that clean themselves up."""

    def create(slug: str = "b"):
        bucket = storage_client.bucket(gcp_target.name(slug))
        bucket.labels = gcp_target.labels
        bucket = storage_client.create_bucket(bucket)
        ledger.add(f"bucket {bucket.name}", lambda: _delete_bucket(bucket))
        return bucket

    return create


@pytest.fixture
def bucket(bucket_factory):
    """One empty bucket for the common single-bucket scenario."""
    return bucket_factory()


def _delete_bucket(bucket) -> None:
    """Delete a bucket and whatever is still in it.

    ``force=True`` makes the client delete the objects first. A bucket already
    gone (the test deleted it itself) is success, not an error.
    """
    from google.api_core import exceptions as gexc

    with contextlib.suppress(gexc.NotFound):
        bucket.delete(force=True)


# -- Pub/Sub ----------------------------------------------------------------


@pytest.fixture
def publisher(gcp_target: Target):
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


@pytest.fixture
def subscriber(gcp_target: Target):
    from google.cloud import pubsub_v1

    return pubsub_v1.SubscriberClient()


@pytest.fixture
def topic_factory(publisher, gcp_target: Target, ledger: Ledger):
    """Create labelled topics that clean themselves up."""

    def create(slug: str = "t") -> str:
        path = gcp_target.topic_path(slug)
        publisher.create_topic(request={"name": path, "labels": gcp_target.labels})
        ledger.add(f"topic {path}", lambda: _delete_topic(publisher, path))
        return path

    return create


@pytest.fixture
def topic(topic_factory) -> str:
    return topic_factory()


@pytest.fixture
def subscription_factory(subscriber, gcp_target: Target, ledger: Ledger):
    """Create labelled subscriptions that clean themselves up."""

    def create(topic_path: str, slug: str = "s", **options) -> str:
        path = gcp_target.subscription_path(slug)
        request = {
            "name": path,
            "topic": topic_path,
            "labels": gcp_target.labels,
            **options,
        }
        subscriber.create_subscription(request=request)
        ledger.add(
            f"subscription {path}", lambda: _delete_subscription(subscriber, path)
        )
        return path

    return create


@pytest.fixture
def subscription(subscription_factory, topic: str) -> str:
    return subscription_factory(topic)


def _delete_topic(publisher, path: str) -> None:
    from google.api_core import exceptions as gexc

    with contextlib.suppress(gexc.NotFound):
        publisher.delete_topic(request={"topic": path})


def _delete_subscription(subscriber, path: str) -> None:
    from google.api_core import exceptions as gexc

    with contextlib.suppress(gexc.NotFound):
        subscriber.delete_subscription(request={"subscription": path})


# -- session sweep ----------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def sweep_leftovers(fidelity_run_id: str) -> Iterator[None]:
    """Delete anything this run's label is on that teardown missed.

    Only meaningful live: under the mock the backend is thrown away with the
    scope. A crashed test cannot run its own deleter, so without this a failed
    live run would leave billable resources behind.
    """
    yield
    if not live_requests_allowed():
        return
    prefix = f"{FIDELITY_PREFIX}-{fidelity_run_id}-"
    _sweep_storage(prefix)
    _sweep_pubsub(prefix, live_project())


def _sweep_storage(prefix: str) -> None:
    from google.cloud import storage

    client = storage.Client(project=live_project())
    for bucket in client.list_buckets():
        if bucket.name.startswith(prefix):
            _delete_bucket(bucket)


def _sweep_pubsub(prefix: str, project: str) -> None:
    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()
    project_path = f"projects/{project}"
    for sub in subscriber.list_subscriptions(request={"project": project_path}):
        if sub.name.rsplit("/", 1)[-1].startswith(prefix):
            _delete_subscription(subscriber, sub.name)

    publisher = pubsub_v1.PublisherClient()
    for found in publisher.list_topics(request={"project": project_path}):
        if found.name.rsplit("/", 1)[-1].startswith(prefix):
            _delete_topic(publisher, found.name)


def pytest_report_header() -> str:
    """Say which target the fidelity suite is pointed at, so a run is unambiguous."""
    if live_requests_allowed():
        return f"drongo fidelity: LIVE against project {live_project()!r}"
    return (
        "drongo fidelity: mock "
        f"(set {ALLOW_LIVE_ENV}=true and {PROJECT_ENV} to verify against real GCP)"
    )
