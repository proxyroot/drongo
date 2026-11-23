"""Cloud Storage fidelity scenarios.

Each test asserts on behaviour real GCS exhibits: status codes mapped to
``google.api_core`` exception types, generation/metageneration transitions, and
which fields the server fills in. Volatile values (etags, timestamps, the actual
generation numbers, which are microsecond timestamps in real GCS and a counter
in drongo) are never asserted on.
"""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from . import gcp_verified, known_gap

# -- generations and metagenerations ----------------------------------------


@gcp_verified
def test_overwrite_advances_generation(bucket) -> None:
    """A new upload to the same name is a new generation, not an edit."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("v1")
    first = blob.generation

    blob.upload_from_string("v2")

    assert blob.generation > first
    assert bucket.blob("obj.txt").download_as_bytes() == b"v2"


@gcp_verified
def test_metadata_patch_advances_metageneration_only(bucket) -> None:
    """Editing metadata bumps metageneration and leaves the generation alone."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("payload")
    generation, metageneration = blob.generation, blob.metageneration

    blob.metadata = {"team": "payments"}
    blob.patch()

    assert blob.generation == generation
    assert blob.metageneration > metageneration


@gcp_verified
def test_new_generation_resets_metageneration(bucket) -> None:
    """Each generation starts its own metageneration at 1."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("v1")
    blob.metadata = {"k": "v"}
    blob.patch()
    assert blob.metageneration > 1

    blob.upload_from_string("v2")

    assert blob.metageneration == 1


# -- preconditions ----------------------------------------------------------


@gcp_verified
def test_if_generation_match_current_succeeds(bucket) -> None:
    """Passing the generation you last saw is the normal optimistic-write path."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("v1")

    blob.upload_from_string("v2", if_generation_match=blob.generation)

    assert bucket.blob("obj.txt").download_as_bytes() == b"v2"


@gcp_verified
@known_gap("drongo ignores ifGenerationMatch, so a stale write is not rejected")
def test_if_generation_match_stale_is_rejected(bucket) -> None:
    """A write guarded by a superseded generation must fail, not clobber."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("v1")
    stale = blob.generation
    blob.upload_from_string("v2")

    with pytest.raises(gexc.PreconditionFailed):
        blob.upload_from_string("v3", if_generation_match=stale)


@gcp_verified
@known_gap("drongo ignores ifGenerationMatch=0, so it does not enforce create-only")
def test_if_generation_match_zero_rejects_existing_object(bucket) -> None:
    """``ifGenerationMatch=0`` means "only if absent", so it fails if present."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("v1")

    with pytest.raises(gexc.PreconditionFailed):
        blob.upload_from_string("v2", if_generation_match=0)


@gcp_verified
def test_if_generation_match_zero_allows_new_object(bucket) -> None:
    """The same guard succeeds when the object really is absent."""
    bucket.blob("fresh.txt").upload_from_string("v1", if_generation_match=0)

    assert bucket.blob("fresh.txt").download_as_bytes() == b"v1"


@gcp_verified
@known_gap("drongo ignores ifMetagenerationMatch on object patch")
def test_if_metageneration_match_stale_is_rejected(bucket) -> None:
    """Metadata edits can be guarded the same way as content writes."""
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("payload")
    stale = blob.metageneration
    blob.metadata = {"first": "1"}
    blob.patch()

    blob.metadata = {"second": "2"}
    with pytest.raises(gexc.PreconditionFailed):
        blob.patch(if_metageneration_match=stale)


# -- error semantics --------------------------------------------------------


@gcp_verified
def test_download_missing_object_is_not_found(bucket) -> None:
    with pytest.raises(gexc.NotFound):
        bucket.blob("absent.txt").download_as_bytes()


@gcp_verified
def test_get_missing_bucket_is_not_found(storage_client, gcp_target) -> None:
    with pytest.raises(gexc.NotFound):
        storage_client.get_bucket(gcp_target.name("never-created"))


@gcp_verified
def test_recreating_own_bucket_conflicts(storage_client, bucket) -> None:
    """Re-creating a bucket you already own is a 409, not a silent no-op."""
    with pytest.raises(gexc.Conflict):
        storage_client.create_bucket(bucket.name)


@gcp_verified
def test_deleting_non_empty_bucket_conflicts(bucket) -> None:
    bucket.blob("obj.txt").upload_from_string("payload")

    with pytest.raises(gexc.Conflict):
        bucket.delete()


@gcp_verified
def test_delete_then_get_is_not_found(bucket) -> None:
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("payload")

    blob.delete()

    assert bucket.blob("obj.txt").exists() is False
    with pytest.raises(gexc.NotFound):
        bucket.blob("obj.txt").download_as_bytes()


# -- listing ----------------------------------------------------------------


@gcp_verified
def test_delimiter_listing_splits_names_from_prefixes(storage_client, bucket) -> None:
    """``delimiter="/"`` returns objects at the level plus synthetic prefixes."""
    for name in ["a/1.txt", "a/b/2.txt", "top.txt"]:
        bucket.blob(name).upload_from_string("x")

    iterator = storage_client.list_blobs(bucket.name, delimiter="/")
    names = [blob.name for blob in iterator]

    assert names == ["top.txt"]
    assert iterator.prefixes == {"a/"}


@gcp_verified
def test_prefix_listing_is_scoped_to_the_prefix(storage_client, bucket) -> None:
    for name in ["logs/1.txt", "logs/2.txt", "other/3.txt"]:
        bucket.blob(name).upload_from_string("x")

    names = [b.name for b in storage_client.list_blobs(bucket.name, prefix="logs/")]

    assert names == ["logs/1.txt", "logs/2.txt"]


@gcp_verified
@known_gap("drongo ignores maxResults/pageToken and returns every object in one page")
def test_list_pages_honour_max_results(storage_client, bucket) -> None:
    """A page holds at most ``max_results`` objects.

    Iterating the whole result hides this: what differs is the page size, which
    is what a test exercising paging logic depends on.
    """
    for index in range(5):
        bucket.blob(f"obj-{index}.txt").upload_from_string("x")

    pages = storage_client.list_blobs(bucket.name, max_results=2).pages

    assert len(list(next(pages))) == 2


@gcp_verified
def test_listing_yields_every_object_regardless_of_page_size(
    storage_client, bucket
) -> None:
    """Whatever the page size, iterating the result returns everything."""
    for index in range(5):
        bucket.blob(f"obj-{index}.txt").upload_from_string("x")

    names = [b.name for b in storage_client.list_blobs(bucket.name, max_results=2)]

    assert len(names) == 5


# -- content ----------------------------------------------------------------


@gcp_verified
def test_reload_populates_server_computed_fields(bucket) -> None:
    """Size, content type and checksums come back from the server, not the client."""
    bucket.blob("obj.txt").upload_from_string("hello world", content_type="text/plain")

    blob = bucket.blob("obj.txt")
    blob.reload()

    assert blob.size == len(b"hello world")
    assert blob.content_type == "text/plain"
    assert blob.md5_hash
    assert blob.etag


@gcp_verified
def test_ranged_download_end_is_inclusive(bucket) -> None:
    """GCS range reads are inclusive of ``end``, unlike Python slicing."""
    bucket.blob("obj.txt").upload_from_string("abcdefghij")

    chunk = bucket.blob("obj.txt").download_as_bytes(start=2, end=4)

    assert chunk == b"cde"


@gcp_verified
def test_copy_is_independent_of_its_source(bucket_factory) -> None:
    """A copy is a snapshot: later writes to the source do not follow it."""
    src, dst = bucket_factory("src"), bucket_factory("dst")
    src.blob("orig.txt").upload_from_string("v1")

    src.copy_blob(src.blob("orig.txt"), dst, "copy.txt")
    src.blob("orig.txt").upload_from_string("v2")

    assert dst.blob("copy.txt").download_as_bytes() == b"v1"


@gcp_verified
def test_make_public_grants_all_users_read(bucket) -> None:
    blob = bucket.blob("obj.txt")
    blob.upload_from_string("payload")

    blob.make_public()
    blob.acl.reload()

    assert ("allUsers", "READER") in [(e["entity"], e["role"]) for e in blob.acl]
