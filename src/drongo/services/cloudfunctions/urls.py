"""URL routing table for Cloud Functions (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.cloudfunctions.responses import CloudFunctionsResponse as _R

_LOC = r"/v2/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_FN = _LOC + r"/functions/(?P<function>[^/:]+)"
_OP = _LOC + r"/operations/(?P<operation>[^/]+)"

url_bases = [r"https?://cloudfunctions\.googleapis\.com"]

url_paths = {
    # Custom verb first.
    f"POST {_LOC}/functions:generateUploadUrl": _R.generate_upload_url,
    # Collection + resource.
    f"POST {_LOC}/functions": _R.create_function,
    f"GET {_LOC}/functions": _R.list_functions,
    f"GET {_FN}": _R.get_function,
    f"PATCH {_FN}": _R.update_function,
    f"DELETE {_FN}": _R.delete_function,
    # Long-running operations.
    f"GET {_OP}": _R.get_operation,
}
