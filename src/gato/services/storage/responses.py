"""HTTP handlers implementing the Cloud Storage JSON API."""

from __future__ import annotations

import json

from gato.core import exceptions
from gato.core.credentials import DEFAULT_PROJECT
from gato.core.responses import BaseResponse, HttpResponse, Request, json_response
from gato.services.storage.models import (
    STORAGE_ENDPOINT,
    Blob,
    StorageBackend,
    storage_backends,
)

# Cloud Storage buckets are a single global namespace, so every project shares
# one backend; the exact key is irrelevant (see ``global_namespace=True``).
_GLOBAL = "_global_"


class StorageResponse(BaseResponse):
    """Handles GCS JSON-API requests against the in-memory backend."""

    @property
    def backend(self) -> StorageBackend:
        return storage_backends[_GLOBAL]

    # -- buckets -----------------------------------------------------------

    def insert_bucket(self, request: Request) -> HttpResponse:
        body = request.json()
        name = body.get("name") or request.param("name")
        if not name:
            raise exceptions.bad_request("Required parameter: name")
        bucket = self.backend.create_bucket(
            name,
            request.param("project") or DEFAULT_PROJECT,
            location=body.get("location", "US"),
            storage_class=body.get("storageClass", "STANDARD"),
            labels=body.get("labels"),
        )
        return json_response(bucket.to_resource())

    def list_buckets(self, request: Request) -> HttpResponse:
        buckets = self.backend.list_buckets(request.param("project"))
        return json_response(
            {
                "kind": "storage#buckets",
                "items": [bucket.to_resource() for bucket in buckets],
            }
        )

    def get_bucket(self, request: Request) -> HttpResponse:
        bucket = self.backend.get_bucket(request.path_params["bucket"])
        return json_response(bucket.to_resource())

    def patch_bucket(self, request: Request) -> HttpResponse:
        bucket = self.backend.get_bucket(request.path_params["bucket"])
        body = request.json()
        if "labels" in body:
            bucket.labels = dict(body["labels"] or {})
        if "storageClass" in body:
            bucket.storage_class = body["storageClass"]
        versioning = body.get("versioning")
        if isinstance(versioning, dict) and "enabled" in versioning:
            bucket.versioning_enabled = bool(versioning["enabled"])
        bucket.metageneration += 1
        return json_response(bucket.to_resource())

    def delete_bucket(self, request: Request) -> HttpResponse:
        self.backend.delete_bucket(request.path_params["bucket"])
        return 204, {}, ""

    # -- object uploads ----------------------------------------------------

    def upload_object(self, request: Request) -> HttpResponse:
        bucket = request.path_params["bucket"]
        upload_type = request.param("uploadType", "media")

        if upload_type == "resumable":
            return self._start_resumable(request, bucket)

        if upload_type == "multipart":
            metadata, data, data_content_type = _parse_multipart_related(
                request.body, request.header("Content-Type", "") or ""
            )
            name = self._require_name(metadata.get("name") or request.param("name"))
            blob = self.backend.put_blob(
                bucket,
                name,
                data,
                content_type=metadata.get("contentType") or data_content_type,
                metadata=metadata.get("metadata"),
            )
            return json_response(blob.to_resource())

        # Simple media upload: the raw body is the object's bytes.
        name = self._require_name(request.param("name"))
        blob = self.backend.put_blob(
            bucket,
            name,
            request.body,
            content_type=request.header("Content-Type"),
        )
        return json_response(blob.to_resource())

    def _start_resumable(self, request: Request, bucket: str) -> HttpResponse:
        metadata = request.json()
        name = self._require_name(metadata.get("name") or request.param("name"))
        upload_id = f"gato-upload-{self.backend.tick()}"
        self.backend.resumable_uploads[upload_id] = {
            "bucket": bucket,
            "name": name,
            "content_type": metadata.get("contentType")
            or request.header("X-Upload-Content-Type"),
            "metadata": metadata.get("metadata"),
            "data": bytearray(),
        }
        location = (
            f"{STORAGE_ENDPOINT}/upload/storage/v1/b/{bucket}/o"
            f"?uploadType=resumable&upload_id={upload_id}"
        )
        return 200, {"Location": location, "Content-Type": "application/json"}, ""

    def resumable_put(self, request: Request) -> HttpResponse:
        upload_id = request.param("upload_id") or ""
        session = self.backend.resumable_uploads.get(upload_id)
        if session is None:
            raise exceptions.not_found("No such upload session")

        session["data"].extend(request.body)
        received = len(session["data"])

        is_final, total = _parse_content_range(request.header("Content-Range"))
        if not is_final:
            end = max(received - 1, 0)
            return 308, {"Range": f"bytes=0-{end}"}, ""

        self.backend.resumable_uploads.pop(upload_id, None)
        blob = self.backend.put_blob(
            session["bucket"],
            session["name"],
            bytes(session["data"]),
            content_type=session["content_type"],
            metadata=session["metadata"],
        )
        return json_response(blob.to_resource())

    # -- object reads ------------------------------------------------------

    def list_objects(self, request: Request) -> HttpResponse:
        blobs, prefixes = self.backend.list_blobs(
            request.path_params["bucket"],
            prefix=request.param("prefix"),
            delimiter=request.param("delimiter"),
        )
        body: dict = {"kind": "storage#objects"}
        if blobs:
            body["items"] = [blob.to_resource() for blob in blobs]
        if prefixes:
            body["prefixes"] = prefixes
        return json_response(body)

    def get_object(self, request: Request) -> HttpResponse:
        bucket = request.path_params["bucket"]
        name = request.path_params["object"]
        if request.param("alt") == "media":
            return self._serve_media(request, bucket, name)
        blob = self.backend.get_blob(bucket, name)
        return json_response(blob.to_resource())

    def download_object(self, request: Request) -> HttpResponse:
        return self._serve_media(
            request, request.path_params["bucket"], request.path_params["object"]
        )

    def _serve_media(self, request: Request, bucket: str, name: str) -> HttpResponse:
        blob = self.backend.get_blob(bucket, name)
        headers = {
            "Content-Type": blob.content_type,
            "ETag": blob.etag,
            "X-Goog-Generation": str(blob.generation),
            "X-Goog-Metageneration": str(blob.metageneration),
            "X-Goog-Stored-Content-Length": str(blob.size),
            "X-Goog-Hash": _goog_hash(blob),
        }

        data, status, extra = _apply_range(blob.data, request.header("Range"))
        headers.update(extra)
        headers["Content-Length"] = str(len(data))
        return status, headers, data

    # -- object writes -----------------------------------------------------

    def patch_object(self, request: Request) -> HttpResponse:
        blob = self.backend.get_blob(
            request.path_params["bucket"], request.path_params["object"]
        )
        body = request.json()
        if "contentType" in body:
            blob.content_type = body["contentType"]
        if "metadata" in body:
            incoming = body["metadata"] or {}
            # A null value removes a key; otherwise merge.
            for key, value in incoming.items():
                if value is None:
                    blob.metadata.pop(key, None)
                else:
                    blob.metadata[key] = value
        if "cacheControl" in body:
            blob.cache_control = body["cacheControl"]
        blob.metageneration += 1
        return json_response(blob.to_resource())

    def delete_object(self, request: Request) -> HttpResponse:
        self.backend.delete_blob(
            request.path_params["bucket"], request.path_params["object"]
        )
        return 204, {}, ""

    def rewrite_object(self, request: Request) -> HttpResponse:
        blob = self.backend.copy_blob(
            request.path_params["src_bucket"],
            request.path_params["src_object"],
            request.path_params["dst_bucket"],
            request.path_params["dst_object"],
        )
        return json_response(
            {
                "kind": "storage#rewriteResponse",
                "totalBytesRewritten": str(blob.size),
                "objectSize": str(blob.size),
                "done": True,
                "resource": blob.to_resource(),
            }
        )

    def copy_object(self, request: Request) -> HttpResponse:
        blob = self.backend.copy_blob(
            request.path_params["src_bucket"],
            request.path_params["src_object"],
            request.path_params["dst_bucket"],
            request.path_params["dst_object"],
        )
        return json_response(blob.to_resource())

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _require_name(name: str | None) -> str:
        if not name:
            raise exceptions.bad_request(
                "Cannot determine object name for upload", reason="required"
            )
        return name


# --- module-level helpers --------------------------------------------------


def _goog_hash(blob: Blob) -> str:
    parts: list[str] = []
    if blob.crc32c is not None:
        parts.append(f"crc32c={blob.crc32c}")
    parts.append(f"md5={blob.md5_hash}")
    return ",".join(parts)


def _apply_range(
    data: bytes, range_header: str | None
) -> tuple[bytes, int, dict[str, str]]:
    """Honour a simple ``Range: bytes=start-end`` header if present."""
    if not range_header or not range_header.startswith("bytes="):
        return data, 200, {}
    spec = range_header[len("bytes=") :].split(",")[0].strip()
    start_s, _, end_s = spec.partition("-")
    try:
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else len(data) - 1
    except ValueError:
        return data, 200, {}
    end = min(end, len(data) - 1)
    if start > end:
        return b"", 200, {}
    chunk = data[start : end + 1]
    headers = {"Content-Range": f"bytes {start}-{end}/{len(data)}"}
    return chunk, 206, headers


def _parse_content_range(header: str | None) -> tuple[bool, int | None]:
    """Return ``(is_final_chunk, total_size)`` for a ``Content-Range`` header."""
    if not header:
        return True, None
    spec = header.replace("bytes ", "").strip()
    range_part, _, total_part = spec.partition("/")
    if total_part in ("", "*"):
        return False, None
    total = int(total_part)
    _, _, end_s = range_part.partition("-")
    if range_part == "*":
        return True, total
    try:
        end = int(end_s)
    except ValueError:
        return True, total
    return end + 1 >= total, total


def _parse_multipart_related(
    body: bytes, content_type: str
) -> tuple[dict, bytes, str | None]:
    """Parse a ``multipart/related`` upload body into ``(metadata, data, ct)``."""
    boundary = _extract_boundary(content_type)
    if boundary is None:
        # No boundary: treat the whole body as JSON metadata (no data).
        return (json.loads(body.decode("utf-8")) if body else {}), b"", None

    marker = b"--" + boundary.encode("utf-8")
    metadata: dict = {}
    data = b""
    data_content_type: str | None = None

    for segment in body.split(marker):
        if segment in (b"", b"--", b"--\r\n", b"\r\n"):
            continue
        part = segment
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if part.startswith(b"--"):  # trailing close delimiter
            continue

        raw_headers, _, content = part.partition(b"\r\n\r\n")
        part_type = ""
        for line in raw_headers.split(b"\r\n"):
            if b":" in line:
                key, _, value = line.partition(b":")
                if key.strip().lower() == b"content-type":
                    part_type = value.strip().decode("utf-8")

        if part_type.startswith("application/json"):
            metadata = json.loads(content.decode("utf-8")) if content else {}
        else:
            data = content
            data_content_type = part_type or None

    return metadata, data, data_content_type


def _extract_boundary(content_type: str) -> str | None:
    for token in content_type.split(";"):
        token = token.strip()
        if token.lower().startswith("boundary="):
            return token[len("boundary=") :].strip('"')
    return None
