"""URL routing table for Memorystore (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.memorystore.responses import MemorystoreResponse as _R

_LOC = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_INST = _LOC + r"/instances/(?P<instance>[^/:]+)"
_OP = _LOC + r"/operations/(?P<operation>[^/]+)"

url_bases = [r"https?://redis\.googleapis\.com"]

url_paths = {
    f"POST {_LOC}/instances": _R.create_instance,
    f"GET {_LOC}/instances": _R.list_instances,
    f"GET {_INST}": _R.get_instance,
    f"PATCH {_INST}": _R.update_instance,
    f"DELETE {_INST}": _R.delete_instance,
    f"GET {_OP}": _R.get_operation,
}
