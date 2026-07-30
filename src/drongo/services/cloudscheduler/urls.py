"""URL routing table for Cloud Scheduler (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.cloudscheduler.responses import SchedulerResponse

_LOC = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_JOB = _LOC + r"/jobs/(?P<job>[^/:]+)"

url_bases = [r"https?://cloudscheduler\.googleapis\.com"]

url_paths = {
    # Custom verbs (most specific first).
    f"POST {_JOB}:pause": SchedulerResponse.pause_job,
    f"POST {_JOB}:resume": SchedulerResponse.resume_job,
    f"POST {_JOB}:run": SchedulerResponse.run_job,
    # Collection + resource.
    f"POST {_LOC}/jobs": SchedulerResponse.create_job,
    f"GET {_LOC}/jobs": SchedulerResponse.list_jobs,
    f"GET {_JOB}": SchedulerResponse.get_job,
    f"PATCH {_JOB}": SchedulerResponse.update_job,
    f"DELETE {_JOB}": SchedulerResponse.delete_job,
}
