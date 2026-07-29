"""URL routing table for Resource Manager (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.resourcemanager.responses import ResourceManagerResponse

_V3 = r"/v3"
_PROJECT = _V3 + r"/projects/(?P<project>[^/:]+)"

url_bases = [r"https?://cloudresourcemanager\.googleapis\.com"]

url_paths = {
    # Collection-level (most specific first).
    f"POST {_V3}/projects": ResourceManagerResponse.create_project,
    f"GET {_V3}/projects:search": ResourceManagerResponse.search_projects,
    f"GET {_V3}/projects": ResourceManagerResponse.list_projects,
    # Resource-level, with custom verbs before the bare name.
    f"POST {_PROJECT}:undelete": ResourceManagerResponse.undelete_project,
    f"PATCH {_PROJECT}": ResourceManagerResponse.update_project,
    f"DELETE {_PROJECT}": ResourceManagerResponse.delete_project,
    f"GET {_PROJECT}": ResourceManagerResponse.get_project,
    # Long-running operations.
    f"GET {_V3}/operations/(?P<operation>.+)": ResourceManagerResponse.get_operation,
}
