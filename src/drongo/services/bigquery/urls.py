"""URL routing table for BigQuery (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.bigquery.responses import BigQueryResponse

_P = r"/bigquery/v2/projects/(?P<project>[^/]+)"
_D = _P + r"/datasets/(?P<dataset>[^/]+)"
_T = _D + r"/tables/(?P<table>[^/]+)"
_J = _P + r"/jobs/(?P<job>[^/]+)"
_Q = _P + r"/queries/(?P<job>[^/]+)"

url_bases = [r"https?://bigquery\.googleapis\.com"]

url_paths = {
    # Query + jobs.
    f"POST {_P}/jobs": BigQueryResponse.insert_job,
    f"POST {_P}/queries": BigQueryResponse.query,
    f"GET {_Q}": BigQueryResponse.get_query_results,
    f"GET {_J}": BigQueryResponse.get_job,
    # Table data (most specific first).
    f"POST {_T}/insertAll": BigQueryResponse.insert_all,
    f"GET {_T}/data": BigQueryResponse.list_table_data,
    # Tables.
    f"POST {_D}/tables": BigQueryResponse.insert_table,
    f"GET {_D}/tables": BigQueryResponse.list_tables,
    f"GET {_T}": BigQueryResponse.get_table,
    f"PATCH {_T}": BigQueryResponse.patch_table,
    f"PUT {_T}": BigQueryResponse.patch_table,
    f"DELETE {_T}": BigQueryResponse.delete_table,
    # Datasets.
    f"POST {_P}/datasets": BigQueryResponse.insert_dataset,
    f"GET {_P}/datasets": BigQueryResponse.list_datasets,
    f"GET {_D}": BigQueryResponse.get_dataset,
    f"PATCH {_D}": BigQueryResponse.patch_dataset,
    f"PUT {_D}": BigQueryResponse.patch_dataset,
    f"DELETE {_D}": BigQueryResponse.delete_dataset,
}
