"""In-process emulators for transports the HTTP layer cannot intercept.

Storage and Secret Manager speak HTTP, so drongo serves them by intercepting
``requests`` with ``responses``. gRPC-first services (Pub/Sub, Firestore) cannot
be intercepted that way: ``grpcio`` is a compiled HTTP/2 stack with no
pure-Python seam to patch. Instead, drongo starts a real in-process server for
those services and redirects the client to it via the service's emulator
environment variable (e.g. ``PUBSUB_EMULATOR_HOST``), exactly how Google's own
emulators work. The client uses its normal (default) transport with no code
change.

A :class:`BaseEmulator` is started when a :func:`drongo.mock_gcp` scope opens and
stopped when it closes. Implementations should be lazy and graceful: if the
required libraries (``grpcio`` and the service client) are not installed,
:meth:`start` should no-op so drongo still works for other services.
"""

from __future__ import annotations

import abc


class BaseEmulator(abc.ABC):
    """A service mock exposed as an in-process server behind an emulator env var."""

    @abc.abstractmethod
    def start(self) -> None:
        """Start the server and point the client at it (set the env var)."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop the server and restore the environment."""
