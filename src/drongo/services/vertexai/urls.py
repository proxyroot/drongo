"""URL routing table for Vertex AI (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.vertexai.responses import VertexAIResponse as R

_P = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_DATASET = _P + r"/datasets/(?P<dataset>[^/:]+)"
_ENDPOINT = _P + r"/endpoints/(?P<endpoint>[^/:]+)"
_MODEL = _P + r"/models/(?P<model>[^/:]+)"
_CJOB = _P + r"/customJobs/(?P<job>[^/:]+)"
_BJOB = _P + r"/batchPredictionJobs/(?P<job>[^/:]+)"

# Vertex AI uses regional endpoints (e.g. us-central1-aiplatform.googleapis.com)
# and the global one; match both.
url_bases = [r"https?://([a-z0-9-]+-)?aiplatform\.googleapis\.com"]

url_paths = {
    # Long-running operation polling.
    f"GET {_P}/operations/(?P<operation>[^/:]+)": R.get_operation,
    # Datasets.
    f"POST {_P}/datasets": R.create_dataset,
    f"GET {_P}/datasets": R.list_datasets,
    f"GET {_DATASET}": R.get_dataset,
    f"DELETE {_DATASET}": R.delete_dataset,
    # Endpoints.
    f"POST {_P}/endpoints": R.create_endpoint,
    f"GET {_P}/endpoints": R.list_endpoints,
    f"GET {_ENDPOINT}": R.get_endpoint,
    f"DELETE {_ENDPOINT}": R.delete_endpoint,
    # Models (upload is a custom verb; created via LRO).
    f"POST {_P}/models:upload": R.upload_model,
    f"GET {_P}/models": R.list_models,
    f"GET {_MODEL}": R.get_model,
    f"DELETE {_MODEL}": R.delete_model,
    # Custom jobs (custom verb first).
    f"POST {_CJOB}:cancel": R.cancel_custom_job,
    f"POST {_P}/customJobs": R.create_custom_job,
    f"GET {_P}/customJobs": R.list_custom_jobs,
    f"GET {_CJOB}": R.get_custom_job,
    f"DELETE {_CJOB}": R.delete_custom_job,
    # Batch prediction jobs (custom verb first).
    f"POST {_BJOB}:cancel": R.cancel_batch_prediction_job,
    f"POST {_P}/batchPredictionJobs": R.create_batch_prediction_job,
    f"GET {_P}/batchPredictionJobs": R.list_batch_prediction_jobs,
    f"GET {_BJOB}": R.get_batch_prediction_job,
    f"DELETE {_BJOB}": R.delete_batch_prediction_job,
}
