"""Google BigQuery mock (REST/JSON API).

Registers the ``bigquery`` service with the drongo engine on import.
"""

from __future__ import annotations

from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.bigquery import urls
from drongo.services.bigquery.models import BigQueryBackend, bigquery_backends
from drongo.services.bigquery.responses import BigQueryResponse

__all__ = ["BigQueryBackend", "BigQueryResponse", "bigquery_backends"]

register_service(
    ServiceDefinition(
        name="bigquery",
        backends=bigquery_backends,
        response=BigQueryResponse(urls.url_bases, urls.url_paths),
    )
)
