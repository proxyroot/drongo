"""URL routing table for Cloud Run Jobs (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.cloudrun.responses import CloudRunResponse

_P = r"/v2/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_J = _P + r"/jobs/(?P<job>[^/:]+)"
_E = _J + r"/executions/(?P<execution>[^/:]+)"

url_bases = [r"https?://run\.googleapis\.com"]

url_paths = {
    # Long-running operation polling.
    f"GET {_P}/operations/(?P<operation>[^/:]+)": CloudRunResponse.get_operation,
    # Jobs (custom verb first).
    f"POST {_J}:run": CloudRunResponse.run_job,
    f"POST {_P}/jobs": CloudRunResponse.create_job,
    f"GET {_P}/jobs": CloudRunResponse.list_jobs,
    f"GET {_J}": CloudRunResponse.get_job,
    f"DELETE {_J}": CloudRunResponse.delete_job,
    # Executions.
    f"GET {_J}/executions": CloudRunResponse.list_executions,
    f"GET {_E}": CloudRunResponse.get_execution,
    f"DELETE {_E}": CloudRunResponse.delete_execution,
}
