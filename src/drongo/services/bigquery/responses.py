"""HTTP handlers implementing the BigQuery REST (v2) API (resource + data)."""

from __future__ import annotations

import json
from typing import Any

from drongo.core import exceptions
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
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
        if not field_names and table.rows:
            field_names = list(table.rows[0].keys())
        fv_rows = [
            {"f": [{"v": _cell(row.get(name))} for name in field_names]}
            for row in table.rows
        ]
        return json_response(
            {
                "kind": "bigquery#tableDataList",
                "totalRows": str(len(table.rows)),
                "rows": fv_rows,
            }
        )


def _cell(value: Any) -> Any:
    """Render a value in BigQuery's ``{"v": ...}`` cell format (scalars only)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)
