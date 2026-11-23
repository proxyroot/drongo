"""URL routing table for Storage Transfer (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.storagetransfer.responses import StorageTransferResponse as R

_JOB = r"/v1/transferJobs/(?P<job>[^:]+)"
_OP = r"/v1/transferOperations/(?P<operation>[^:]+)"
_POOLS = r"/v1/projects/(?P<project>[^/]+)/agentPools"
_POOL = _POOLS + r"/(?P<pool>[^/]+)"

url_bases = [r"https?://([a-z0-9-]+-)?storagetransfer\.googleapis\.com"]

url_paths = {
    # Google service account.
    r"GET /v1/googleServiceAccounts/(?P<project>[^/]+)": R.get_google_service_account,
    # Transfer jobs (custom verb + collection before item routes).
    f"POST {_JOB}:run": R.run_transfer_job,
    "POST /v1/transferJobs": R.create_transfer_job,
    "GET /v1/transferJobs": R.list_transfer_jobs,
    f"GET {_JOB}": R.get_transfer_job,
    f"PATCH {_JOB}": R.update_transfer_job,
    f"DELETE {_JOB}": R.delete_transfer_job,
    # Transfer operations (custom verbs first).
    f"POST {_OP}:pause": R.pause_transfer_operation,
    f"POST {_OP}:resume": R.resume_transfer_operation,
    f"POST {_OP}:cancel": R.cancel_transfer_operation,
    "GET /v1/transferOperations": R.list_transfer_operations,
    f"GET {_OP}": R.get_transfer_operation,
    # Agent pools.
    f"POST {_POOLS}": R.create_agent_pool,
    f"GET {_POOLS}": R.list_agent_pools,
    f"GET {_POOL}": R.get_agent_pool,
    f"PATCH {_POOL}": R.update_agent_pool,
    f"DELETE {_POOL}": R.delete_agent_pool,
}
