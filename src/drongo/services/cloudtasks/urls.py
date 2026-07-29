"""URL routing table for Cloud Tasks (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.cloudtasks.responses import CloudTasksResponse

_P = r"/v2/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_Q = _P + r"/queues/(?P<queue>[^/:]+)"
_T = _Q + r"/tasks/(?P<task>[^/:]+)"

url_bases = [r"https?://cloudtasks\.googleapis\.com"]

url_paths = {
    # Custom verbs (with a ':') first.
    f"POST {_T}:run": CloudTasksResponse.run_task,
    f"POST {_Q}:purge": CloudTasksResponse.purge_queue,
    f"POST {_Q}:pause": CloudTasksResponse.pause_queue,
    f"POST {_Q}:resume": CloudTasksResponse.resume_queue,
    # Tasks.
    f"POST {_Q}/tasks": CloudTasksResponse.create_task,
    f"GET {_Q}/tasks": CloudTasksResponse.list_tasks,
    f"GET {_T}": CloudTasksResponse.get_task,
    f"DELETE {_T}": CloudTasksResponse.delete_task,
    # Queues.
    f"POST {_P}/queues": CloudTasksResponse.create_queue,
    f"GET {_P}/queues": CloudTasksResponse.list_queues,
    f"GET {_Q}": CloudTasksResponse.get_queue,
    f"DELETE {_Q}": CloudTasksResponse.delete_queue,
}
