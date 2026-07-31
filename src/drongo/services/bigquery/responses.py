"""HTTP handlers implementing the BigQuery REST (v2) API (resource + data + query)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.bigquery import sql
from drongo.services.bigquery.models import BigQueryBackend, bigquery_backends


class BigQueryResponse(BaseResponse):
    """Handles BigQuery REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> BigQueryBackend:
        return bigquery_backends[request.path_params["project"]]

    # -- datasets ----------------------------------------------------------

    def insert_dataset(self, request: Request) -> HttpResponse:
        body = request.json()
        reference = body.get("datasetReference", {})
        dataset_id = reference.get("datasetId")
        if not dataset_id:
            raise exceptions.bad_request("Required field: datasetReference.datasetId")
        dataset = self.backend_for(request).create_dataset(
            dataset_id,
            location=body.get("location", "US"),
            labels=body.get("labels"),
        )
        return json_response(dataset.to_resource())

    def list_datasets(self, request: Request) -> HttpResponse:
        datasets = self.backend_for(request).list_datasets()
        return json_response(
            {
                "kind": "bigquery#datasetList",
                "datasets": [dataset.list_item() for dataset in datasets],
            }
        )

    def get_dataset(self, request: Request) -> HttpResponse:
        dataset = self.backend_for(request).get_dataset(request.path_params["dataset"])
        return json_response(dataset.to_resource())

    def patch_dataset(self, request: Request) -> HttpResponse:
        dataset = self.backend_for(request).get_dataset(request.path_params["dataset"])
        body = request.json()
        if "labels" in body:
            dataset.labels = dict(body["labels"] or {})
        return json_response(dataset.to_resource())

    def delete_dataset(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_dataset(request.path_params["dataset"])
        return 204, {}, ""

    # -- tables ------------------------------------------------------------

    def insert_table(self, request: Request) -> HttpResponse:
        body = request.json()
        reference = body.get("tableReference", {})
        table_id = reference.get("tableId")
        if not table_id:
            raise exceptions.bad_request("Required field: tableReference.tableId")
        schema = (body.get("schema") or {}).get("fields")
        table = self.backend_for(request).create_table(
            request.path_params["dataset"],
            table_id,
            schema=schema,
            labels=body.get("labels"),
        )
        return json_response(table.to_resource())

    def list_tables(self, request: Request) -> HttpResponse:
        tables = self.backend_for(request).list_tables(request.path_params["dataset"])
        return json_response(
            {
                "kind": "bigquery#tableList",
                "tables": [table.list_item() for table in tables],
                "totalItems": len(tables),
            }
        )

    def get_table(self, request: Request) -> HttpResponse:
        table = self.backend_for(request).get_table(
            request.path_params["dataset"], request.path_params["table"]
        )
        return json_response(table.to_resource())

    def patch_table(self, request: Request) -> HttpResponse:
        table = self.backend_for(request).get_table(
            request.path_params["dataset"], request.path_params["table"]
        )
        body = request.json()
        if "labels" in body:
            table.labels = dict(body["labels"] or {})
        if "schema" in body and body["schema"]:
            table.schema = list(body["schema"].get("fields", []))
        return json_response(table.to_resource())

    def delete_table(self, request: Request) -> HttpResponse:
        self.backend_for(request).delete_table(
            request.path_params["dataset"], request.path_params["table"]
        )
        return 204, {}, ""

    # -- table data --------------------------------------------------------

    def insert_all(self, request: Request) -> HttpResponse:
        body = request.json()
        rows = [row.get("json", {}) for row in body.get("rows", [])]
        self.backend_for(request).insert_rows(
            request.path_params["dataset"], request.path_params["table"], rows
        )
        return json_response({"kind": "bigquery#tableDataInsertAllResponse"})

    def list_table_data(self, request: Request) -> HttpResponse:
        table = self.backend_for(request).get_table(
            request.path_params["dataset"], request.path_params["table"]
        )
        field_names = [f["name"] for f in table.schema]
        field_types = {f["name"]: f.get("type", "STRING") for f in table.schema}
        if not field_names and table.rows:
            field_names = list(table.rows[0].keys())
        fv_rows = [
            {
                "f": [
                    {"v": _cell(row.get(name), field_types.get(name))}
                    for name in field_names
                ]
            }
            for row in table.rows
        ]
        return json_response(
            {
                "kind": "bigquery#tableDataList",
                "totalRows": str(len(table.rows)),
                "rows": fv_rows,
            }
        )

    # -- query jobs --------------------------------------------------------

    def insert_job(self, request: Request) -> HttpResponse:
        """jobs.insert. Runs a query job to completion; ignores other job types."""
        backend = self.backend_for(request)
        body = request.json()
        reference = body.get("jobReference") or {}
        job_id = reference.get("jobId") or uuid.uuid4().hex
        location = reference.get("location") or "US"
        query_config = (body.get("configuration") or {}).get("query")
        if query_config is not None:
            schema, rows = sql.run_query(backend, query_config.get("query", ""))
            backend.save_query_job(
                job_id, query_config.get("query", ""), schema, rows, location=location
            )
        return json_response(
            _job_resource(request.path_params["project"], job_id, body)
        )

    def get_job(self, request: Request) -> HttpResponse:
        """jobs.get. Query jobs complete synchronously, so always DONE."""
        backend = self.backend_for(request)
        job = backend.get_query_job(request.path_params["job"])
        return json_response(_completed_job(request.path_params["project"], job))

    def get_query_results(self, request: Request) -> HttpResponse:
        """jobs.getQueryResults: the schema + rows for a completed query job."""
        backend = self.backend_for(request)
        job = backend.get_query_job(request.path_params["job"])
        return json_response(_query_results(request.path_params["project"], job))

    def query(self, request: Request) -> HttpResponse:
        """jobs.query: run a query and return its results in one call."""
        backend = self.backend_for(request)
        body = request.json()
        query_text = body.get("query", "")
        job_id = (body.get("jobReference") or {}).get("jobId") or uuid.uuid4().hex
        location = body.get("location") or "US"
        schema, rows = sql.run_query(backend, query_text)
        job = backend.save_query_job(
            job_id, query_text, schema, rows, location=location
        )
        return json_response(
            _query_results(
                request.path_params["project"], job, kind="bigquery#queryResponse"
            )
        )


def _job_resource(project: str, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """A DONE job echoing back the submitted configuration (jobs.insert)."""
    reference = body.get("jobReference") or {}
    location = reference.get("location") or "US"
    return {
        "kind": "bigquery#job",
        "etag": job_id,
        "id": f"{project}:{location}.{job_id}",
        "selfLink": (
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}"
            f"/jobs/{job_id}"
        ),
        "jobReference": {"projectId": project, "jobId": job_id, "location": location},
        "configuration": body.get("configuration") or {"jobType": "QUERY"},
        "status": {"state": "DONE"},
        "statistics": {"query": {"totalBytesProcessed": "0"}},
    }


def _completed_job(project: str, job: dict[str, Any]) -> dict[str, Any]:
    """A DONE query job rebuilt from stored state (jobs.get)."""
    return _job_resource(
        project,
        job["job_id"],
        {
            "jobReference": {"location": job["location"]},
            "configuration": {
                "jobType": "QUERY",
                "query": {"query": job["sql"], "useLegacySql": False},
            },
        },
    )


def _query_results(
    project: str, job: dict[str, Any], *, kind: str = "bigquery#getQueryResultsResponse"
) -> dict[str, Any]:
    schema, rows = job["schema"], job["rows"]
    fv_rows = [
        {"f": [{"v": _cell(row.get(f["name"]), f["type"])} for f in schema]}
        for row in rows
    ]
    return {
        "kind": kind,
        "etag": job["job_id"],
        "schema": {"fields": [_schema_field(f) for f in schema]},
        "jobReference": {
            "projectId": project,
            "jobId": job["job_id"],
            "location": job["location"],
        },
        "totalRows": str(len(rows)),
        "rows": fv_rows,
        "totalBytesProcessed": "0",
        "jobComplete": True,
        "cacheHit": False,
    }


def _schema_field(field: dict[str, Any]) -> dict[str, Any]:
    return {"name": field["name"], "type": field["type"], "mode": "NULLABLE"}


def _cell(value: Any, field_type: str | None = None) -> Any:
    """Render a value in BigQuery's ``{"v": ...}`` cell format (scalars only)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if field_type and field_type.upper() == "TIMESTAMP":
        return _timestamp_cell(value)
    return str(value)


def _timestamp_cell(value: Any) -> str:
    """Render a TIMESTAMP as epoch microseconds.

    ``tabledata.list`` always returns TIMESTAMP columns as microseconds since
    the Unix epoch, which is what google-cloud-bigquery's ``timestamp_to_py``
    parses with ``int(value)``. Inserts, however, may supply an ISO-8601 string
    or epoch seconds, so normalise whatever was stored to the wire format.
    Values we cannot interpret are passed through unchanged.
    """
    if isinstance(value, datetime):
        return _micros(value)
    if isinstance(value, (int, float)):
        return str(round(float(value) * 1_000_000))

    text = str(value).strip()
    try:  # epoch seconds supplied as a string
        return str(round(float(text) * 1_000_000))
    except ValueError:
        pass

    candidate = text[:-4].strip() if text.upper().endswith(" UTC") else text
    if candidate.endswith(("Z", "z")):  # Python 3.10's fromisoformat rejects "Z"
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return _micros(datetime.fromisoformat(candidate))
    except ValueError:
        return text


def _micros(moment: datetime) -> str:
    """Epoch microseconds for ``moment``, treating naive values as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return str(round(moment.timestamp() * 1_000_000))
