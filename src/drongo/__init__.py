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

from drongo.core.decorator import mock_gcp
from drongo.core.exceptions import DrongoHttpError
from drongo.core.registry import get_backend, reset_all_backends

__all__ = [
    "DrongoHttpError",
    "__version__",
    "get_backend",
    "mock_gcp",
    "reset_all_backends",
]

# The version is derived from the git tag at build time by hatch-vcs, which
# writes ``_version.py``. The fallback keeps imports working in a source tree
# that has not been built yet.
try:
    from drongo._version import __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0+unknown"
