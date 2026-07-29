"""URL routing table for Cloud Storage (moto-style ``url_bases``/``url_paths``).

``url_paths`` maps ``"<METHOD> <path-regex>"`` to a
:class:`~gato.services.storage.responses.StorageResponse` handler. The path
regex is matched against the URL path with :func:`re.fullmatch`; the first match
wins, so more specific paths are listed first.
"""

from __future__ import annotations

from gato.services.storage.responses import StorageResponse

url_bases = [r"https?://storage\.googleapis\.com"]

url_paths = {
    # Uploads and downloads live under dedicated path prefixes.
    r"POST /upload/storage/v1/b/(?P<bucket>[^/]+)/o": StorageResponse.upload_object,
    r"PUT /upload/storage/v1/b/(?P<bucket>[^/]+)/o": StorageResponse.resumable_put,
    r"GET /download/storage/v1/b/(?P<bucket>[^/]+)/o/(?P<object>[^/]+)": (
        StorageResponse.download_object
    ),
    # Buckets.
    r"POST /storage/v1/b": StorageResponse.insert_bucket,
    r"GET /storage/v1/b": StorageResponse.list_buckets,
    r"GET /storage/v1/b/(?P<bucket>[^/]+)": StorageResponse.get_bucket,
    r"PATCH /storage/v1/b/(?P<bucket>[^/]+)": StorageResponse.patch_bucket,
    r"PUT /storage/v1/b/(?P<bucket>[^/]+)": StorageResponse.patch_bucket,
    r"DELETE /storage/v1/b/(?P<bucket>[^/]+)": StorageResponse.delete_bucket,
    # Objects.
    r"GET /storage/v1/b/(?P<bucket>[^/]+)/o": StorageResponse.list_objects,
    (
        r"POST /storage/v1/b/(?P<src_bucket>[^/]+)/o/(?P<src_object>[^/]+)"
        r"/rewriteTo/b/(?P<dst_bucket>[^/]+)/o/(?P<dst_object>[^/]+)"
    ): StorageResponse.rewrite_object,
    (
        r"POST /storage/v1/b/(?P<src_bucket>[^/]+)/o/(?P<src_object>[^/]+)"
        r"/copyTo/b/(?P<dst_bucket>[^/]+)/o/(?P<dst_object>[^/]+)"
    ): StorageResponse.copy_object,
    r"GET /storage/v1/b/(?P<bucket>[^/]+)/o/(?P<object>[^/]+)": (
        StorageResponse.get_object
    ),
    r"PATCH /storage/v1/b/(?P<bucket>[^/]+)/o/(?P<object>[^/]+)": (
        StorageResponse.patch_object
    ),
    r"DELETE /storage/v1/b/(?P<bucket>[^/]+)/o/(?P<object>[^/]+)": (
        StorageResponse.delete_object
    ),
}
