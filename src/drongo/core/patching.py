"""Force gRPC-default clients onto their REST transport during a mock scope.

Some services default to gRPC but also ship a REST transport *and* have no
emulator environment variable (Cloud Tasks, Cloud Run). For those, the cleanest
transparent approach is to make the client use its REST transport while a
:func:`drongo.mock_gcp` scope is active, so the existing HTTP interception layer
serves it. The user's code keeps its default client, unchanged.

A service lists the GAPIC client classes to redirect; :func:`force_rest_patchers`
returns ``unittest.mock`` patchers that wrap their ``__init__`` to inject
``transport="rest"`` and anonymous credentials. Missing clients (library not
installed) are skipped.
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest import mock


def force_rest_patchers(client_specs: list[tuple[str, str]]) -> list[Any]:
    """Return patchers forcing the given ``(module, class_name)`` clients to REST."""
    try:
        from google.auth.credentials import AnonymousCredentials

        anonymous: Any = AnonymousCredentials()
    except ImportError:  # pragma: no cover - google libs optional
        anonymous = None

    patchers: list[Any] = []
    for module_path, class_name in client_specs:
        try:
            client_cls = getattr(importlib.import_module(module_path), class_name)
        except (ImportError, AttributeError):
            continue  # client library not installed: nothing to patch
        patchers.append(_patch_transport(client_cls, anonymous))
    return patchers


def _patch_transport(client_cls: Any, anonymous: Any) -> Any:
    original_init = client_cls.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = "rest"
        if not kwargs.get("credentials") and anonymous is not None:
            kwargs["credentials"] = anonymous
        original_init(self, *args, **kwargs)

    return mock.patch.object(client_cls, "__init__", patched_init)
