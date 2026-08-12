"""drongo - mock Google Cloud Platform services in your tests.

drongo is to Google Cloud what `moto <https://github.com/getmoto/moto>`_ is to AWS:
an in-memory, in-process fake of GCP service APIs so you can test code that talks
to Google Cloud without touching the network, standing up an emulator, or paying
for real resources.

Basic usage::

    from drongo import mock_gcp

    @mock_gcp
    def test_upload():
        from google.cloud import storage

        client = storage.Client(project="test")
        bucket = client.create_bucket("my-bucket")
        bucket.blob("hello.txt").upload_from_string("hi")

        assert bucket.blob("hello.txt").download_as_text() == "hi"
"""

from __future__ import annotations

import importlib
from types import ModuleType

from drongo.core.decorator import mock_gcp
from drongo.core.exceptions import DrongoHttpError
from drongo.core.registry import get_backend, reset_all_backends

#: Service subpackages reachable as ``drongo.<name>`` (e.g. ``drongo.cloudrun``)
#: for their public helpers, such as the executable-handler decorators.
_SERVICE_MODULES = frozenset(
    {
        "artifactregistry",
        "bigquery",
        "bigtable",
        "cloudfunctions",
        "cloudrun",
        "cloudscheduler",
        "cloudtasks",
        "datastore",
        "documentai",
        "firestore",
        "iam",
        "kms",
        "logging",
        "memorystore",
        "monitoring",
        "pubsub",
        "resourcemanager",
        "secretmanager",
        "storage",
        "vertexai",
    }
)

__all__ = [
    "DrongoHttpError",
    "__version__",
    "get_backend",
    "mock_gcp",
    "reset_all_backends",
    *sorted(_SERVICE_MODULES),
]


def __getattr__(name: str) -> ModuleType:
    """Lazily import a service subpackage as an attribute of ``drongo``.

    Keeps ``import drongo`` cheap while allowing ``from drongo import cloudrun``
    (and ``drongo.cloudrun.job_handler(...)``) without an eager import cycle.
    """
    if name in _SERVICE_MODULES:
        return importlib.import_module(f"drongo.services.{name}")
    raise AttributeError(f"module 'drongo' has no attribute {name!r}")


# The version is derived from the git tag at build time by hatch-vcs, which
# writes ``_version.py``. The fallback keeps imports working in a source tree
# that has not been built yet.
try:
    from drongo._version import __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"
