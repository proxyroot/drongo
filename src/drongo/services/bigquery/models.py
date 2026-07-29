"""In-memory models for Google BigQuery (REST/JSON API).

Scoped to resource + data management, which is what is faithfully mockable at the
wire level: datasets, tables, streaming inserts (``insertAll``), and reading rows
back (``tabledata.list``). SQL query *execution* is intentionally out of scope
(it would require a SQL engine); see the docs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

BIGQUERY_ENDPOINT = "https://bigquery.googleapis.com"


def _now_ms() -> str:
    return str(int(time.time() * 1000))


@dataclass
class Table:
    """A BigQuery table: schema plus streamed rows."""

    project: str
    dataset_id: str
    table_id: str
    schema: list[dict[str, Any]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    location: str = "US"
    created_ms: str = field(default_factory=_now_ms)

    @property
    def reference(self) -> dict[str, str]:
        return {
            "projectId": self.project,
            "datasetId": self.dataset_id,
            "tableId": self.table_id,
        }

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "kind": "bigquery#table",
            "id": f"{self.project}:{self.dataset_id}.{self.table_id}",
            "selfLink": (
                f"{BIGQUERY_ENDPOINT}/bigquery/v2/projects/{self.project}"
                f"/datasets/{self.dataset_id}/tables/{self.table_id}"
            ),
            "tableReference": self.reference,
            "type": "TABLE",
            "location": self.location,
            "numRows": str(len(self.rows)),
            "creationTime": self.created_ms,
            "lastModifiedTime": self.created_ms,
            "etag": f"{self.dataset_id}/{self.table_id}",
        }
        if self.schema:
            resource["schema"] = {"fields": self.schema}
        if self.labels:
            resource["labels"] = dict(self.labels)
        return resource

    def list_item(self) -> dict[str, Any]:
        item = {
            "kind": "bigquery#table",
            "id": f"{self.project}:{self.dataset_id}.{self.table_id}",
            "tableReference": self.reference,
            "type": "TABLE",
        }
        if self.schema:
            item["schema"] = {"fields": self.schema}
        return item


@dataclass
class Dataset:
    """A BigQuery dataset containing tables."""

    project: str
    dataset_id: str
    location: str = "US"
    labels: dict[str, str] = field(default_factory=dict)
    created_ms: str = field(default_factory=_now_ms)
    tables: dict[str, Table] = field(default_factory=dict)

    @property
    def reference(self) -> dict[str, str]:
        return {"projectId": self.project, "datasetId": self.dataset_id}

    def to_resource(self) -> dict[str, Any]:
        resource = {
            "kind": "bigquery#dataset",
            "id": f"{self.project}:{self.dataset_id}",
            "selfLink": (
                f"{BIGQUERY_ENDPOINT}/bigquery/v2/projects/{self.project}"
                f"/datasets/{self.dataset_id}"
            ),
            "datasetReference": self.reference,
            "location": self.location,
            "creationTime": self.created_ms,
            "lastModifiedTime": self.created_ms,
            "etag": self.dataset_id,
        }
        if self.labels:
            resource["labels"] = dict(self.labels)
        return resource

    def list_item(self) -> dict[str, Any]:
        return {
            "kind": "bigquery#dataset",
            "id": f"{self.project}:{self.dataset_id}",
            "datasetReference": self.reference,
            "location": self.location,
        }


class BigQueryBackend(BaseBackend):
    """In-memory BigQuery state for a single project."""

    def setup(self) -> None:
        self.datasets: dict[str, Dataset] = {}

    # -- datasets ----------------------------------------------------------

    def create_dataset(
        self,
        dataset_id: str,
        *,
        location: str = "US",
        labels: dict[str, str] | None = None,
    ) -> Dataset:
        if dataset_id in self.datasets:
            raise exceptions.already_exists(
                f"Already Exists: Dataset {self.project}:{dataset_id}"
            )
        dataset = Dataset(
            project=self.project,
            dataset_id=dataset_id,
            location=location or "US",
            labels=dict(labels or {}),
        )
        self.datasets[dataset_id] = dataset
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset:
        try:
            return self.datasets[dataset_id]
        except KeyError:
            raise exceptions.not_found(
                f"Not found: Dataset {self.project}:{dataset_id}"
            )

    def list_datasets(self) -> list[Dataset]:
        return [self.datasets[k] for k in sorted(self.datasets)]

    def delete_dataset(self, dataset_id: str) -> None:
        self.get_dataset(dataset_id)
        del self.datasets[dataset_id]

    # -- tables ------------------------------------------------------------

    def create_table(
        self,
        dataset_id: str,
        table_id: str,
        *,
        schema: list[dict[str, Any]] | None = None,
        labels: dict[str, str] | None = None,
    ) -> Table:
        dataset = self.get_dataset(dataset_id)
        if table_id in dataset.tables:
            raise exceptions.already_exists(
                f"Already Exists: Table {self.project}:{dataset_id}.{table_id}"
            )
        table = Table(
            project=self.project,
            dataset_id=dataset_id,
            table_id=table_id,
            schema=list(schema or []),
            labels=dict(labels or {}),
        )
        dataset.tables[table_id] = table
        return table

    def get_table(self, dataset_id: str, table_id: str) -> Table:
        dataset = self.get_dataset(dataset_id)
        try:
            return dataset.tables[table_id]
        except KeyError:
            raise exceptions.not_found(
                f"Not found: Table {self.project}:{dataset_id}.{table_id}"
            )

    def list_tables(self, dataset_id: str) -> list[Table]:
        dataset = self.get_dataset(dataset_id)
        return [dataset.tables[k] for k in sorted(dataset.tables)]

    def delete_table(self, dataset_id: str, table_id: str) -> None:
        dataset = self.get_dataset(dataset_id)
        if table_id not in dataset.tables:
            raise exceptions.not_found(
                f"Not found: Table {self.project}:{dataset_id}.{table_id}"
            )
        del dataset.tables[table_id]

    # -- table data --------------------------------------------------------

    def insert_rows(
        self, dataset_id: str, table_id: str, rows: list[dict[str, Any]]
    ) -> None:
        table = self.get_table(dataset_id, table_id)
        table.rows.extend(rows)

    def list_rows(self, dataset_id: str, table_id: str) -> list[dict[str, Any]]:
        return list(self.get_table(dataset_id, table_id).rows)


#: Project-keyed backends, inspectable via ``get_backend("bigquery")[project]``.
bigquery_backends: BackendDict[BigQueryBackend] = BackendDict(
    BigQueryBackend, "bigquery"
)
