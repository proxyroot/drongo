"""Shared test helpers."""

from __future__ import annotations

import pytest


@pytest.fixture
def storage_client():
    """A Cloud Storage client wired for the active drongo mock scope."""
    from google.cloud import storage

    return storage.Client(project="test-project")


def new_bucket(name: str = "bucket", project: str = "test-project"):
    from google.cloud import storage

    return storage.Client(project=project).create_bucket(name)
