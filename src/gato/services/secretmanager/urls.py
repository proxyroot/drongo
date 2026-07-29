"""URL routing table for Secret Manager (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from gato.services.secretmanager.responses import SecretManagerResponse

_SECRET = r"/v1/projects/(?P<project>[^/]+)/secrets/(?P<secret>[^/:]+)"
_VERSION = _SECRET + r"/versions/(?P<version>[^/:]+)"

url_bases = [r"https?://secretmanager\.googleapis\.com"]

url_paths = {
    r"POST /v1/projects/(?P<project>[^/]+)/secrets": (
        SecretManagerResponse.create_secret
    ),
    r"GET /v1/projects/(?P<project>[^/]+)/secrets": (
        SecretManagerResponse.list_secrets
    ),
    f"POST {_SECRET}:addVersion": SecretManagerResponse.add_version,
    f"GET {_SECRET}": SecretManagerResponse.get_secret,
    f"PATCH {_SECRET}": SecretManagerResponse.update_secret,
    f"DELETE {_SECRET}": SecretManagerResponse.delete_secret,
    f"GET {_SECRET}/versions": SecretManagerResponse.list_versions,
    f"GET {_VERSION}:access": SecretManagerResponse.access_version,
    f"POST {_VERSION}:destroy": SecretManagerResponse.destroy_version,
    f"POST {_VERSION}:disable": SecretManagerResponse.disable_version,
    f"POST {_VERSION}:enable": SecretManagerResponse.enable_version,
    f"GET {_VERSION}": SecretManagerResponse.get_version,
}
