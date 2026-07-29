"""Neutralise Google credential resolution while mocking.

Outside a real GCP environment, ``google.auth.default()`` raises
``DefaultCredentialsError`` and client libraries try to contact the metadata
server or an OAuth token endpoint. While a :func:`gato.mock_gcp` scope is active
we patch credential discovery to hand back anonymous credentials and a default
project, so ``storage.Client()`` "just works" with no arguments - the moral
equivalent of moto seeding dummy ``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY``.

If ``google.auth`` is not importable (the user has no google libraries) this is
a no-op: there is nothing to mock.
"""

from __future__ import annotations

from unittest import mock

#: Project returned by the patched ``google.auth.default`` when the caller does
#: not specify one.
DEFAULT_PROJECT = "gato-test-project"


def build_patchers() -> list[mock._patch]:
    """Return (unstarted) patchers that neutralise google credential discovery."""
    try:
        import google.auth
        import google.auth.credentials
    except ImportError:  # pragma: no cover - google libs are optional
        return []

    anonymous = google.auth.credentials.AnonymousCredentials()

    def fake_default(*_args: object, **_kwargs: object) -> tuple:
        return anonymous, DEFAULT_PROJECT

    patchers: list[mock._patch] = [mock.patch("google.auth.default", fake_default)]

    # Some libraries import the symbol directly from the private module.
    try:
        import google.auth._default  # noqa: F401

        patchers.append(mock.patch("google.auth._default.default", fake_default))
    except ImportError:  # pragma: no cover
        pass

    return patchers
