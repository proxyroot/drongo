"""Storage depth: object/bucket ACLs, notifications, and signed URLs."""

from __future__ import annotations

import pytest
import requests

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "my-project"


def _client():
    from google.cloud import storage

    return storage.Client(project=PROJECT)


def _blob():
    bucket = _client().create_bucket("mybucket")
    blob = bucket.blob("file.txt")
    blob.upload_from_string(b"hello world", content_type="text/plain")
    return bucket, blob


# -- object ACLs ------------------------------------------------------------


def test_make_public_grants_all_users_read() -> None:
    _, blob = _blob()
    blob.make_public()
    blob.acl.reload()
    assert ("allUsers", "READER") in [(e["entity"], e["role"]) for e in blob.acl]


def test_object_acl_grant_user() -> None:
    _, blob = _blob()
    blob.acl.user("alice@example.com").grant_read()
    blob.acl.save()
    blob.acl.reload()
    assert "user-alice@example.com" in {entry["entity"] for entry in blob.acl}


# -- bucket ACLs ------------------------------------------------------------


def test_bucket_acl_grant_owner() -> None:
    bucket, _ = _blob()
    bucket.acl.user("bob@example.com").grant_owner()
    bucket.acl.save()
    bucket.acl.reload()
    assert ("user-bob@example.com", "OWNER") in [
        (entry["entity"], entry["role"]) for entry in bucket.acl
    ]


# -- notifications ----------------------------------------------------------


def test_notification_create_list_delete() -> None:
    bucket, _ = _blob()
    notification = bucket.notification(
        topic_name="my-topic", topic_project=PROJECT, payload_format="JSON_API_V1"
    )
    notification.create()
    assert notification.notification_id is not None

    listed = list(bucket.list_notifications())
    assert [n.topic_name for n in listed] == ["my-topic"]

    notification.delete()
    assert list(bucket.list_notifications()) == []


# -- signed URLs ------------------------------------------------------------


def test_signed_url_get_serves_object() -> None:
    _, blob = _blob()
    url = blob.generate_signed_url(version="v4", expiration=3600, method="GET")
    assert "storage.googleapis.com/mybucket/file.txt" in url
    response = requests.get(url)
    assert response.status_code == 200
    assert response.content == b"hello world"


def test_signed_url_put_uploads_object() -> None:
    bucket, _ = _blob()
    target = bucket.blob("uploaded.txt")
    url = target.generate_signed_url(version="v4", expiration=3600, method="PUT")
    response = requests.put(
        url, data=b"via signed url", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 200
    assert bucket.blob("uploaded.txt").download_as_bytes() == b"via signed url"
