"""In-memory models for Vertex AI / AI Platform (``aiplatform`` v1).

Vertex AI defaults to gRPC and has no emulator env var, so drongo forces the
service clients onto their REST transport (see ``__init__.py``) and serves them
here. Resources are stored as the proto-JSON the client sent and echoed back on
get/list, so the mock stays faithful without hard-coding every field of these
large protos.

Several mutations are long-running operations (create/delete dataset, endpoint,
model; delete jobs). drongo completes them synchronously: each returns a *done*
``Operation`` with the result embedded, which the operations endpoint replays.
Jobs (custom, batch prediction) are created synchronously and returned directly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["PredictionHandler", "VertexAIBackend", "vertexai_backends"]

#: A prediction handler receives ``(instances, parameters)`` and returns the list
#: of predictions, so a test can run real prediction logic on a mocked endpoint.
PredictionHandler = Callable[[list[Any], dict[str, Any]], list[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class VertexAIBackend(BaseBackend):
    """In-memory Vertex AI state for a single project.

    All resource types share one name-keyed store; the collection segment of a
    resource name (``datasets``, ``endpoints``, ...) keeps them apart.
    """

    def setup(self) -> None:
        self.resources: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.prediction_handlers: dict[str, PredictionHandler] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    # -- long-running operations ------------------------------------------

    def operation(self, parent: str, response: dict[str, Any] | None) -> dict[str, Any]:
        """Record and return a *done* Operation embedding ``response`` (an Any)."""
        name = f"{parent}/operations/{self._next()}"
        op: dict[str, Any] = {"name": name, "done": True}
        if response is not None:
            op["response"] = response
        self.operations[name] = op
        return op

    def get_operation(self, name: str) -> dict[str, Any]:
        # Operations complete immediately; unknown ones are reported done+empty.
        return self.operations.get(name, {"name": name, "done": True})

    # -- generic resource CRUD --------------------------------------------

    def create(
        self,
        parent: str,
        collection: str,
        body: dict[str, Any],
        *,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        resource_id = resource_id or str(self._next())
        name = f"{parent}/{collection}/{resource_id}"
        if name in self.resources:
            raise exceptions.already_exists(f"Resource already exists: {name}")
        resource = dict(body or {})
        resource["name"] = name
        resource.setdefault("createTime", _now())
        resource["updateTime"] = _now()
        self.resources[name] = resource
        return resource

    def get(self, name: str) -> dict[str, Any]:
        try:
            return self.resources[name]
        except KeyError:
            raise exceptions.not_found(f"Resource not found: {name}")

    def list_resources(self, parent: str, collection: str) -> list[dict[str, Any]]:
        prefix = f"{parent}/{collection}/"
        return [
            self.resources[n] for n in sorted(self.resources) if n.startswith(prefix)
        ]

    def delete(self, name: str) -> None:
        self.get(name)  # 404 if missing
        del self.resources[name]

    def set_state(self, name: str, state: str) -> dict[str, Any]:
        resource = self.get(name)
        resource["state"] = state
        resource["updateTime"] = _now()
        return resource

    # -- serving (deploy / undeploy / predict) ----------------------------

    def deploy_model(
        self, endpoint: str, deployed_model: dict[str, Any], traffic_split: dict
    ) -> dict[str, Any]:
        """Attach a model to an endpoint; return the deployed-model resource."""
        resource = self.get(endpoint)
        deployed = dict(deployed_model or {})
        deployed.setdefault("id", str(self._next()))
        resource.setdefault("deployedModels", []).append(deployed)
        if traffic_split:
            resource["trafficSplit"] = dict(traffic_split)
        resource["updateTime"] = _now()
        return deployed

    def undeploy_model(
        self, endpoint: str, deployed_model_id: str, traffic_split: dict
    ) -> None:
        resource = self.get(endpoint)
        resource["deployedModels"] = [
            d
            for d in resource.get("deployedModels", [])
            if d.get("id") != deployed_model_id
        ]
        resource["trafficSplit"] = dict(traffic_split or {})
        resource["updateTime"] = _now()

    def register_prediction_handler(
        self, endpoint: str, handler: PredictionHandler
    ) -> None:
        """Bind a callable that produces predictions for an endpoint's ``predict``."""
        self.prediction_handlers[endpoint] = handler

    def predict(
        self, endpoint: str, instances: list[Any], parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Run the endpoint's registered handler (or return no predictions)."""
        resource = self.get(endpoint)
        handler = self.prediction_handlers.get(endpoint)
        predictions = handler(instances, parameters) if handler is not None else []
        deployed = resource.get("deployedModels") or [{}]
        return {
            "predictions": predictions,
            "deployedModelId": deployed[0].get("id", ""),
            "model": deployed[0].get("model", ""),
        }


#: Project-keyed backends, inspectable via ``get_backend("vertexai")[project]``.
vertexai_backends: BackendDict[VertexAIBackend] = BackendDict(
    VertexAIBackend, "vertexai"
)
