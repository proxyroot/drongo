"""HTTP handlers implementing the Vertex AI REST (v1) API (control plane).

Vertex AI's clients are gRPC-first; drongo forces them onto REST during a mock
scope (see ``__init__.py``). Create/delete of datasets, endpoints and models are
long-running operations, completed synchronously here. Jobs are created and
returned directly.
"""

from __future__ import annotations

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.vertexai.models import VertexAIBackend, vertexai_backends

# The ``@type`` URLs stamped on the Operation envelopes these handlers return.
_TYPE_PREFIX = "type.googleapis.com/google.cloud.aiplatform.v1."
DATASET_TYPE = _TYPE_PREFIX + "Dataset"
ENDPOINT_TYPE = _TYPE_PREFIX + "Endpoint"
UPLOAD_MODEL_RESPONSE_TYPE = _TYPE_PREFIX + "UploadModelResponse"
DEPLOY_MODEL_RESPONSE_TYPE = _TYPE_PREFIX + "DeployModelResponse"
UNDEPLOY_MODEL_RESPONSE_TYPE = _TYPE_PREFIX + "UndeployModelResponse"
EMPTY_TYPE = "type.googleapis.com/google.protobuf.Empty"


class VertexAIResponse(BaseResponse):
    """Handles Vertex AI REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> VertexAIBackend:
        return vertexai_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _name(self, request: Request, collection: str, key: str) -> str:
        return f"{self._parent(request)}/{collection}/{request.path_params[key]}"

    # -- datasets ----------------------------------------------------------

    def create_dataset(self, request: Request) -> HttpResponse:
        parent = self._parent(request)
        backend = self.backend_for(request)
        resource = backend.create(parent, "datasets", request.json())
        return json_response(
            backend.operation(parent, {"@type": DATASET_TYPE, **resource})
        )

    def get_dataset(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get(self._name(request, "datasets", "dataset"))
        )

    def list_datasets(self, request: Request) -> HttpResponse:
        datasets = self.backend_for(request).list_resources(
            self._parent(request), "datasets"
        )
        return json_response({"datasets": datasets})

    def delete_dataset(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._name(request, "datasets", "dataset"))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    # -- endpoints ---------------------------------------------------------

    def create_endpoint(self, request: Request) -> HttpResponse:
        parent = self._parent(request)
        backend = self.backend_for(request)
        resource = backend.create(
            parent, "endpoints", request.json(), resource_id=request.param("endpointId")
        )
        return json_response(
            backend.operation(parent, {"@type": ENDPOINT_TYPE, **resource})
        )

    def get_endpoint(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get(self._name(request, "endpoints", "endpoint"))
        )

    def list_endpoints(self, request: Request) -> HttpResponse:
        endpoints = self.backend_for(request).list_resources(
            self._parent(request), "endpoints"
        )
        return json_response({"endpoints": endpoints})

    def delete_endpoint(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._name(request, "endpoints", "endpoint"))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    def deploy_model(self, request: Request) -> HttpResponse:
        parent = self._parent(request)
        backend = self.backend_for(request)
        body = request.json()
        deployed = backend.deploy_model(
            self._name(request, "endpoints", "endpoint"),
            body.get("deployedModel", {}),
            body.get("trafficSplit", {}),
        )
        response = {"@type": DEPLOY_MODEL_RESPONSE_TYPE, "deployedModel": deployed}
        return json_response(backend.operation(parent, response))

    def undeploy_model(self, request: Request) -> HttpResponse:
        parent = self._parent(request)
        backend = self.backend_for(request)
        body = request.json()
        backend.undeploy_model(
            self._name(request, "endpoints", "endpoint"),
            body.get("deployedModelId", ""),
            body.get("trafficSplit", {}),
        )
        return json_response(
            backend.operation(parent, {"@type": UNDEPLOY_MODEL_RESPONSE_TYPE})
        )

    def predict(self, request: Request) -> HttpResponse:
        body = request.json()
        result = self.backend_for(request).predict(
            self._name(request, "endpoints", "endpoint"),
            body.get("instances", []),
            body.get("parameters", {}),
        )
        return json_response(result)

    # -- models ------------------------------------------------------------

    def upload_model(self, request: Request) -> HttpResponse:
        parent = self._parent(request)
        backend = self.backend_for(request)
        body = request.json()
        resource = backend.create(
            parent, "models", body.get("model", {}), resource_id=body.get("modelId")
        )
        response = {
            "@type": UPLOAD_MODEL_RESPONSE_TYPE,
            "model": resource["name"],
            "modelVersionId": "1",
        }
        return json_response(backend.operation(parent, response))

    def get_model(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get(self._name(request, "models", "model"))
        )

    def list_models(self, request: Request) -> HttpResponse:
        models = self.backend_for(request).list_resources(
            self._parent(request), "models"
        )
        return json_response({"models": models})

    def delete_model(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._name(request, "models", "model"))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    # -- custom jobs (created synchronously) -------------------------------

    def create_custom_job(self, request: Request) -> HttpResponse:
        resource = self.backend_for(request).create(
            self._parent(request), "customJobs", request.json()
        )
        return json_response(resource)

    def get_custom_job(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get(self._name(request, "customJobs", "job"))
        )

    def list_custom_jobs(self, request: Request) -> HttpResponse:
        jobs = self.backend_for(request).list_resources(
            self._parent(request), "customJobs"
        )
        return json_response({"customJobs": jobs})

    def cancel_custom_job(self, request: Request) -> HttpResponse:
        self.backend_for(request).set_state(
            self._name(request, "customJobs", "job"), "JOB_STATE_CANCELLED"
        )
        return json_response({})

    def delete_custom_job(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._name(request, "customJobs", "job"))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    # -- batch prediction jobs (created synchronously) ---------------------

    def create_batch_prediction_job(self, request: Request) -> HttpResponse:
        resource = self.backend_for(request).create(
            self._parent(request), "batchPredictionJobs", request.json()
        )
        return json_response(resource)

    def get_batch_prediction_job(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get(
                self._name(request, "batchPredictionJobs", "job")
            )
        )

    def list_batch_prediction_jobs(self, request: Request) -> HttpResponse:
        jobs = self.backend_for(request).list_resources(
            self._parent(request), "batchPredictionJobs"
        )
        return json_response({"batchPredictionJobs": jobs})

    def cancel_batch_prediction_job(self, request: Request) -> HttpResponse:
        self.backend_for(request).set_state(
            self._name(request, "batchPredictionJobs", "job"), "JOB_STATE_CANCELLED"
        )
        return json_response({})

    def delete_batch_prediction_job(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete(self._name(request, "batchPredictionJobs", "job"))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    # -- operations (LRO polling) ------------------------------------------

    def get_operation(self, request: Request) -> HttpResponse:
        name = f"{self._parent(request)}/operations/{request.path_params['operation']}"
        return json_response(self.backend_for(request).get_operation(name))
