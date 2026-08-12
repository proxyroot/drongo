"""Regression tests for reported Vertex AI issues.

The import of ``aiplatform_v1`` is at module scope (before the ``drongo`` fixture
runs), mirroring how the reporter set up the failing case exactly.
"""

from __future__ import annotations

import pytest
from google.api_core.client_options import ClientOptions

aiplatform_v1 = pytest.importorskip("google.cloud.aiplatform_v1")

pytestmark = pytest.mark.usefixtures("drongo")

LOCATION = "us-central1"
PARENT = f"projects/my-project/locations/{LOCATION}"
_OPTS = ClientOptions(api_endpoint=f"{LOCATION}-aiplatform.googleapis.com")


def test_job_service_client_is_forced_to_rest() -> None:
    """https://github.com/proxyroot/drongo/issues/49

    JobServiceClient must be forced onto its REST transport inside a mock scope
    (so drongo intercepts it) rather than talking real gRPC. Regression added
    after 0.7.0 shipped without the Vertex AI service at all, which left the
    client on gRPC and failing with UNAUTHENTICATED.
    """
    client = aiplatform_v1.JobServiceClient(client_options=_OPTS)
    assert type(client.transport).__name__ == "JobServiceRestTransport"

    job = client.create_batch_prediction_job(
        parent=PARENT,
        batch_prediction_job=aiplatform_v1.BatchPredictionJob(display_name="test"),
    )
    assert job.display_name == "test"
