"""In-memory models for Google Cloud Storage."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend
from drongo.core.utils import crc32c_base64, md5_base64, now_rfc3339

#: Base endpoint used when rendering ``selfLink``/``mediaLink`` fields.
STORAGE_ENDPOINT = "https://storage.googleapis.com"


@dataclass
class HmacKey:
    """An HMAC key for a service account (used for S3-interop / signed URLs)."""

    access_id: str
    service_account_email: str
    project: str
    secret: str
    state: str = "ACTIVE"
    time_created: str = field(default_factory=now_rfc3339)
    updated: str = field(default_factory=now_rfc3339)

    def metadata_resource(self) -> dict[str, Any]:
        return {
            "kind": "storage#hmacKeyMetadata",
            "id": f"{self.project}/{self.access_id}",
            "accessId": self.access_id,
            "projectId": self.project,
            "serviceAccountEmail": self.service_account_email,
            "state": self.state,
            "timeCreated": self.time_created,
            "updated": self.updated,
            "etag": f"{self.access_id}/{self.state}",
        }


@dataclass
class Blob:
    """A single stored object and its metadata."""

    bucket_name: str
    name: str
    data: bytes = b""
    content_type: str = "application/octet-stream"
    generation: int = 1
    metageneration: int = 1
    storage_class: str = "STANDARD"
    metadata: dict[str, str] = field(default_factory=dict)
    cache_control: str | None = None
    content_encoding: str | None = None
    content_disposition: str | None = None
    content_language: str | None = None
    time_created: str = field(default_factory=now_rfc3339)
    updated: str = field(default_factory=now_rfc3339)

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def md5_hash(self) -> str:
        return md5_base64(self.data)

    @property
    def crc32c(self) -> str | None:
        return crc32c_base64(self.data)

    @property
    def etag(self) -> str:
        return f"{self.bucket_name}/{self.name}/{self.generation}"

    def to_resource(self) -> dict:
        encoded = quote(self.name, safe="")
        resource: dict = {
            "kind": "storage#object",
            "id": f"{self.bucket_name}/{self.name}/{self.generation}",
            "selfLink": (
                f"{STORAGE_ENDPOINT}/storage/v1/b/{self.bucket_name}/o/{encoded}"
            ),
            "mediaLink": (
                f"{STORAGE_ENDPOINT}/download/storage/v1/b/{self.bucket_name}"
                f"/o/{encoded}?generation={self.generation}&alt=media"
            ),
            "name": self.name,
            "bucket": self.bucket_name,
            "generation": str(self.generation),
            "metageneration": str(self.metageneration),
            "contentType": self.content_type,
            "storageClass": self.storage_class,
            "size": str(self.size),
            "md5Hash": self.md5_hash,
            "etag": self.etag,
            "timeCreated": self.time_created,
            "updated": self.updated,
            "timeStorageClassUpdated": self.time_created,
        }
        if self.crc32c is not None:
            resource["crc32c"] = self.crc32c
        if self.metadata:
            resource["metadata"] = dict(self.metadata)
        for key, value in (
            ("cacheControl", self.cache_control),
            ("contentEncoding", self.content_encoding),
            ("contentDisposition", self.content_disposition),
            ("contentLanguage", self.content_language),
        ):
            if value is not None:
                resource[key] = value
        return resource


@dataclass
class Bucket:
    """A storage bucket and the objects it holds."""

    name: str
    project: str
    location: str = "US"
    storage_class: str = "STANDARD"
    metageneration: int = 1
    versioning_enabled: bool = False
    labels: dict[str, str] = field(default_factory=dict)
    time_created: str = field(default_factory=now_rfc3339)
    updated: str = field(default_factory=now_rfc3339)
    blobs: dict[str, Blob] = field(default_factory=dict)
    iam_policy: dict[str, Any] | None = None

    def to_resource(self) -> dict:
        resource: dict = {
            "kind": "storage#bucket",
            "id": self.name,
            "selfLink": f"{STORAGE_ENDPOINT}/storage/v1/b/{self.name}",
            "name": self.name,
            "projectNumber": "000000000000",
            "metageneration": str(self.metageneration),
            "location": self.location,
            "storageClass": self.storage_class,
            "etag": f"{self.name}/{self.metageneration}",
            "timeCreated": self.time_created,
            "updated": self.updated,
            "iamConfiguration": {
                "bucketPolicyOnly": {"enabled": False},
                "uniformBucketLevelAccess": {"enabled": False},
            },
            "versioning": {"enabled": self.versioning_enabled},
        }
        if self.labels:
            resource["labels"] = dict(self.labels)
        return resource


class StorageBackend(BaseBackend):
    """In-memory Cloud Storage state (buckets live in one global namespace)."""

    def setup(self) -> None:
        self.buckets: dict[str, Bucket] = {}
        # Live resumable-upload sessions keyed by upload id (see the responses).
        self.resumable_uploads: dict[str, dict] = {}
        self.hmac_keys: dict[str, HmacKey] = {}
        self._clock = 1

    # -- bucket IAM policy -------------------------------------------------

    def get_iam_policy(self, bucket_name: str) -> dict[str, Any]:
        bucket = self.get_bucket(bucket_name)
        if bucket.iam_policy is None:
            return {
                "kind": "storage#policy",
                "resourceId": f"projects/_/buckets/{bucket_name}",
                "version": 1,
                "bindings": [],
                "etag": "CAE=",
            }
        return bucket.iam_policy

    def set_iam_policy(
        self, bucket_name: str, policy: dict[str, Any]
    ) -> dict[str, Any]:
        bucket = self.get_bucket(bucket_name)
        stored = {
            "kind": "storage#policy",
            "resourceId": f"projects/_/buckets/{bucket_name}",
            "version": policy.get("version", 1),
            "bindings": policy.get("bindings", []),
            "etag": policy.get("etag", "CAE="),
        }
        bucket.iam_policy = stored
        return stored

    # -- HMAC keys ---------------------------------------------------------

    def create_hmac_key(self, project: str, email: str) -> HmacKey:
        access_id = f"GOOG{self._tick():032X}"
        secret = base64.b64encode(f"drongo-secret-{access_id}".encode()).decode("ascii")
        key = HmacKey(
            access_id=access_id,
            service_account_email=email,
            project=project,
            secret=secret,
        )
        self.hmac_keys[access_id] = key
        return key

    def list_hmac_keys(self, project: str) -> list[HmacKey]:
        return sorted(
            (k for k in self.hmac_keys.values() if k.project == project),
            key=lambda k: k.access_id,
        )

    def get_hmac_key(self, access_id: str) -> HmacKey:
        try:
            return self.hmac_keys[access_id]
        except KeyError:
            raise exceptions.not_found(f"HMAC key not found: {access_id}")

    def update_hmac_key(self, access_id: str, state: str) -> HmacKey:
        key = self.get_hmac_key(access_id)
        key.state = state
        key.updated = now_rfc3339()
        return key

    def delete_hmac_key(self, access_id: str) -> None:
        key = self.get_hmac_key(access_id)
        if key.state != "INACTIVE":
            raise exceptions.bad_request(
                "HMAC key must be INACTIVE before it can be deleted"
            )
        del self.hmac_keys[access_id]

    def tick(self) -> int:
        """Public monotonic counter used for generations and upload ids."""
        return self._tick()

    def _tick(self) -> int:
        value = self._clock
        self._clock += 1
        return value

    # -- buckets -----------------------------------------------------------

    def create_bucket(
        self,
        name: str,
        project: str,
        *,
        location: str = "US",
        storage_class: str = "STANDARD",
        labels: dict[str, str] | None = None,
    ) -> Bucket:
        if name in self.buckets:
            raise exceptions.already_exists(
                f"Your previous request to create the named bucket succeeded "
                f"and you already own it: {name}"
            )
        bucket = Bucket(
            name=name,
            project=project,
            location=(location or "US").upper(),
            storage_class=storage_class or "STANDARD",
            labels=dict(labels or {}),
        )
        self.buckets[name] = bucket
        return bucket

    def get_bucket(self, name: str) -> Bucket:
        try:
            return self.buckets[name]
        except KeyError:
            raise exceptions.not_found(f"The specified bucket does not exist: {name}")

    def list_buckets(self, project: str | None = None) -> list[Bucket]:
        buckets = sorted(self.buckets.values(), key=lambda b: b.name)
        if project is None:
            return buckets
        return [b for b in buckets if b.project == project]

    def delete_bucket(self, name: str, *, force: bool = False) -> None:
        bucket = self.get_bucket(name)
        if bucket.blobs and not force:
            raise exceptions.already_exists(
                f"The bucket you tried to delete is not empty: {name}",
                reason="notEmpty",
            )
        del self.buckets[name]

    # -- blobs -------------------------------------------------------------

    def put_blob(
        self,
        bucket_name: str,
        name: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Blob:
        bucket = self.get_bucket(bucket_name)
        generation = self._tick()
        blob = Blob(
            bucket_name=bucket_name,
            name=name,
            data=data,
            content_type=content_type or "application/octet-stream",
            generation=generation,
            metadata=dict(metadata or {}),
        )
        bucket.blobs[name] = blob
        return blob

    def get_blob(self, bucket_name: str, name: str) -> Blob:
        bucket = self.get_bucket(bucket_name)
        try:
            return bucket.blobs[name]
        except KeyError:
            raise exceptions.not_found(f"No such object: {bucket_name}/{name}")

    def list_blobs(
        self,
        bucket_name: str,
        *,
        prefix: str | None = None,
        delimiter: str | None = None,
    ) -> tuple[list[Blob], list[str]]:
        bucket = self.get_bucket(bucket_name)
        blobs: list[Blob] = []
        prefixes: set = set()
        prefix = prefix or ""
        for blob in sorted(bucket.blobs.values(), key=lambda b: b.name):
            if not blob.name.startswith(prefix):
                continue
            if delimiter:
                rest = blob.name[len(prefix) :]
                if delimiter in rest:
                    head = rest.split(delimiter, 1)[0]
                    prefixes.add(prefix + head + delimiter)
                    continue
            blobs.append(blob)
        return blobs, sorted(prefixes)

    def delete_blob(self, bucket_name: str, name: str) -> None:
        bucket = self.get_bucket(bucket_name)
        if name not in bucket.blobs:
            raise exceptions.not_found(f"No such object: {bucket_name}/{name}")
        del bucket.blobs[name]

    def copy_blob(
        self,
        src_bucket: str,
        src_name: str,
        dst_bucket: str,
        dst_name: str,
    ) -> Blob:
        source = self.get_blob(src_bucket, src_name)
        self.get_bucket(dst_bucket)  # ensure destination exists
        return self.put_blob(
            dst_bucket,
            dst_name,
            source.data,
            content_type=source.content_type,
            metadata=dict(source.metadata),
        )


#: Project-keyed backends. Buckets are a global namespace (like S3 in moto), so
#: every project shares one backend. Inspect via ``get_backend("storage")[p]``.
storage_backends: BackendDict[StorageBackend] = BackendDict(
    StorageBackend, "storage", global_namespace=True
)
