"""Vertex AI tests using the real aiplatform_v1 clients (forced REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc
from google.api_core.client_options import ClientOptions

pytest.importorskip("google.cloud.aiplatform_v1")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
LOCATION = "us-central1"
PARENT = f"projects/{PROJECT}/locations/{LOCATION}"
_OPTS = ClientOptions(api_endpoint=f"{LOCATION}-aiplatform.googleapis.com")


def _dataset_client():
    from google.cloud import aiplatform_v1

    return aiplatform_v1.DatasetServiceClient(client_options=_OPTS)


def _endpoint_client():
    from google.cloud import aiplatform_v1

    return aiplatform_v1.EndpointServiceClient(client_options=_OPTS)


def _model_client():
    from google.cloud import aiplatform_v1

    return aiplatform_v1.ModelServiceClient(client_options=_OPTS)


def _job_client():
    from google.cloud import aiplatform_v1

    return aiplatform_v1.JobServiceClient(client_options=_OPTS)


# -- datasets ---------------------------------------------------------------


def test_dataset_create_get_list_delete() -> None:
    from google.cloud import aiplatform_v1

    client = _dataset_client()
    dataset = client.create_dataset(
        parent=PARENT,
        dataset=aiplatform_v1.Dataset(
            display_name="my-ds", metadata_schema_uri="gs://schema"
        ),
    ).result()  # LRO completes synchronously
    assert dataset.display_name == "my-ds"
    assert dataset.name.startswith(f"{PARENT}/datasets/")

    assert client.get_dataset(name=dataset.name).display_name == "my-ds"
    assert [d.display_name for d in client.list_datasets(parent=PARENT)] == ["my-ds"]

    client.delete_dataset(name=dataset.name).result()
    assert list(client.list_datasets(parent=PARENT)) == []


def test_get_missing_dataset_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _dataset_client().get_dataset(name=f"{PARENT}/datasets/ghost")


# -- endpoints --------------------------------------------------------------


def test_endpoint_create_get_list_delete() -> None:
    from google.cloud import aiplatform_v1

    client = _endpoint_client()
    endpoint = client.create_endpoint(
        parent=PARENT, endpoint=aiplatform_v1.Endpoint(display_name="my-ep")
    ).result()
    assert endpoint.display_name == "my-ep"

    assert client.get_endpoint(name=endpoint.name).display_name == "my-ep"
    assert [e.display_name for e in client.list_endpoints(parent=PARENT)] == ["my-ep"]

    client.delete_endpoint(name=endpoint.name).result()
    assert list(client.list_endpoints(parent=PARENT)) == []


def test_deploy_undeploy_model() -> None:
    from google.cloud import aiplatform_v1

    endpoints = _endpoint_client()
    endpoint = endpoints.create_endpoint(
        parent=PARENT, endpoint=aiplatform_v1.Endpoint(display_name="serve")
    ).result()
    model = (
        _model_client()
        .upload_model(parent=PARENT, model=aiplatform_v1.Model(display_name="m"))
        .result()
        .model
    )

    deployed = endpoints.deploy_model(
        endpoint=endpoint.name,
        deployed_model=aiplatform_v1.DeployedModel(model=model, display_name="dm"),
        traffic_split={"0": 100},
    ).result()
    dm_id = deployed.deployed_model.id
    assert deployed.deployed_model.model == model
    assert [
        d.id for d in endpoints.get_endpoint(name=endpoint.name).deployed_models
    ] == [dm_id]

    endpoints.undeploy_model(endpoint=endpoint.name, deployed_model_id=dm_id).result()
    assert list(endpoints.get_endpoint(name=endpoint.name).deployed_models) == []


def test_predict_runs_registered_handler() -> None:
    from google.cloud import aiplatform_v1

    from drongo.services import vertexai

    endpoint = (
        _endpoint_client()
        .create_endpoint(
            parent=PARENT, endpoint=aiplatform_v1.Endpoint(display_name="serve")
        )
        .result()
    )

    @vertexai.prediction_handler(endpoint.name)
    def handler(instances, parameters):
        return [{"score": len(instances)} for _ in instances]

    from google.cloud import aiplatform_v1 as v1

    predictions = v1.PredictionServiceClient(client_options=_OPTS).predict(
        endpoint=endpoint.name, instances=[{"a": 1}, {"b": 2}]
    )
    assert [dict(p) for p in predictions.predictions] == [
        {"score": 2},
        {"score": 2},
    ]


def test_predict_without_handler_returns_no_predictions() -> None:
    from google.cloud import aiplatform_v1

    endpoint = (
        _endpoint_client()
        .create_endpoint(
            parent=PARENT, endpoint=aiplatform_v1.Endpoint(display_name="serve")
        )
        .result()
    )
    response = aiplatform_v1.PredictionServiceClient(client_options=_OPTS).predict(
        endpoint=endpoint.name, instances=[{"a": 1}]
    )
    assert list(response.predictions) == []


# -- models -----------------------------------------------------------------


def test_model_upload_get_list_delete() -> None:
    from google.cloud import aiplatform_v1

    client = _model_client()
    response = client.upload_model(
        parent=PARENT, model=aiplatform_v1.Model(display_name="my-model")
    ).result()
    assert response.model.startswith(f"{PARENT}/models/")

    model = client.get_model(name=response.model)
    assert model.display_name == "my-model"
    assert [m.display_name for m in client.list_models(parent=PARENT)] == ["my-model"]

    client.delete_model(name=response.model).result()
    assert list(client.list_models(parent=PARENT)) == []


# -- custom jobs ------------------------------------------------------------


def test_custom_job_create_get_list_cancel_delete() -> None:
    from google.cloud import aiplatform_v1

    client = _job_client()
    job = client.create_custom_job(
        parent=PARENT,
        custom_job=aiplatform_v1.CustomJob(
            display_name="train",
            job_spec=aiplatform_v1.CustomJobSpec(worker_pool_specs=[]),
        ),
    )
    assert job.display_name == "train"
    assert job.name.startswith(f"{PARENT}/customJobs/")

    assert client.get_custom_job(name=job.name).display_name == "train"
    assert [j.display_name for j in client.list_custom_jobs(parent=PARENT)] == ["train"]

    client.cancel_custom_job(name=job.name)
    state = client.get_custom_job(name=job.name).state
    assert state == aiplatform_v1.JobState.JOB_STATE_CANCELLED

    client.delete_custom_job(name=job.name).result()
    assert list(client.list_custom_jobs(parent=PARENT)) == []


# -- batch prediction jobs --------------------------------------------------


def test_batch_prediction_job_create_get_list() -> None:
    from google.cloud import aiplatform_v1

    client = _job_client()
    job = client.create_batch_prediction_job(
        parent=PARENT,
        batch_prediction_job=aiplatform_v1.BatchPredictionJob(display_name="bp"),
    )
    assert job.display_name == "bp"
    assert client.get_batch_prediction_job(name=job.name).display_name == "bp"
    listed = [j.display_name for j in client.list_batch_prediction_jobs(parent=PARENT)]
    assert listed == ["bp"]
