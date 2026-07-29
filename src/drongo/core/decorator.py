"""The public ``mock_gcp`` entry point and the controller behind it.

``mock_gcp`` is deliberately as flexible as moto's ``mock_aws``. It can be used
as:

* a bare decorator - ``@mock_gcp``
* a called decorator - ``@mock_gcp()``
* a context manager - ``with mock_gcp(): ...``
* a class decorator - on a plain test class *or* a ``unittest.TestCase``
  (``setUp``/``tearDown`` are wrapped automatically)

Scopes are reentrant: nesting ``mock_gcp`` scopes shares one set of backends and
only resets state when the outermost scope opens and closes.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import responses

from drongo.core import registry
from drongo.core.credentials import build_patchers

F = TypeVar("F", bound=Callable[..., Any])

_SERVICES_LOADED = False


def _load_services() -> None:
    """Import the services package once so every service self-registers."""
    global _SERVICES_LOADED
    if not _SERVICES_LOADED:
        import drongo.services  # noqa: F401  (import for side effects)

        _SERVICES_LOADED = True


class DrongoController:
    """Process-wide, reentrant controller for the interception layer."""

    def __init__(self) -> None:
        self._depth = 0
        self._responses: responses.RequestsMock | None = None
        self._patchers: list[Any] = []
        self._emulators: list[Any] = []

    @property
    def active(self) -> bool:
        return self._depth > 0

    def start(self) -> None:
        self._depth += 1
        if self._depth > 1:
            return  # already active - nested scope shares state

        _load_services()
        registry.reset_all_backends()

        # HTTP interception for REST/JSON services.
        mock = responses.RequestsMock(assert_all_requests_are_fired=False)
        for service in registry.iter_services():
            if service.response is not None:
                service.response.register(mock)
        mock.start()
        self._responses = mock

        self._patchers = build_patchers()
        for patcher in self._patchers:
            patcher.start()

        # In-process emulators for gRPC-first services (e.g. Pub/Sub). Each is
        # lazy and graceful: start() no-ops if its libraries are unavailable.
        self._emulators = []
        for service in registry.iter_services():
            if service.emulator is not None:
                service.emulator.start()
                self._emulators.append(service.emulator)

    def stop(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        if self._depth > 0:
            return  # inner scope closed; outer scope still owns the mocks

        for emulator in reversed(self._emulators):
            emulator.stop()
        self._emulators = []

        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers = []

        if self._responses is not None:
            self._responses.stop()
            self._responses.reset()
            self._responses = None

        registry.reset_all_backends()


#: The single shared controller for the whole process.
_CONTROLLER = DrongoController()


class DrongoMock:
    """Decorator / context-manager object returned by :func:`mock_gcp`."""

    def __init__(self) -> None:
        self._controller = _CONTROLLER

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> DrongoMock:
        self._controller.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._controller.stop()

    def start(self) -> None:
        """Start mocking (imperative style, mirrors ``responses.start``)."""
        self._controller.start()

    def stop(self) -> None:
        """Stop mocking (imperative style, mirrors ``responses.stop``)."""
        self._controller.stop()

    # -- decorator ---------------------------------------------------------

    def __call__(self, func_or_class: Any) -> Any:
        if isinstance(func_or_class, type):
            return self._decorate_class(func_or_class)
        return self._decorate_callable(func_or_class)

    def _decorate_callable(self, func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with DrongoMock():
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    def _decorate_class(self, klass: type) -> type:
        if issubclass(klass, unittest.TestCase):
            return self._decorate_unittest(klass)

        for name in list(vars(klass)):
            if name.startswith("test"):
                attr = getattr(klass, name)
                if callable(attr):
                    setattr(klass, name, self._decorate_callable(attr))
        return klass

    def _decorate_unittest(self, klass: type[unittest.TestCase]) -> type:
        orig_setup = klass.setUp
        orig_teardown = klass.tearDown

        def setUp(inner_self: Any) -> None:
            mocker = DrongoMock()
            inner_self._drongo_mock = mocker
            mocker.start()
            orig_setup(inner_self)

        def tearDown(inner_self: Any) -> None:
            try:
                orig_teardown(inner_self)
            finally:
                inner_self._drongo_mock.stop()

        # Dynamically wrap the fixture hooks; setattr keeps mypy out of the way.
        setattr(klass, "setUp", setUp)  # noqa: B010
        setattr(klass, "tearDown", tearDown)  # noqa: B010
        return klass


def mock_gcp(func: Any = None) -> Any:
    """Mock every drongo-supported Google Cloud service.

    Works as a bare decorator, a called decorator, a context manager, or a class
    decorator. See the module docstring for examples.
    """
    mocker = DrongoMock()
    if func is not None:
        return mocker(func)
    return mocker
