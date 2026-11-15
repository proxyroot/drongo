# Known gaps

Behaviour real GCP has that drongo does not, each one proved by a scenario in
[`tests/fidelity/`](tests/fidelity).

Every gap here is a `@known_gap(...)` scenario: expected to **fail** under the
mock and to **pass** against real GCP. The xfail is `strict=True`, so closing a
gap turns its scenario into a failure until the marker and its entry below are
removed. The list cannot quietly go stale, and `test_known_gaps_doc.py` fails if
a scenario and this file disagree.

Re-checking a row against the real service, and adding scenarios of your own, is
described in [docs/fidelity.md](docs/fidelity.md).

## Cloud Storage

### Object write preconditions are accepted and ignored

`ifGenerationMatch` and `ifMetagenerationMatch` are parsed off the request and
dropped, so drongo never answers `412 Precondition Failed`. Code that relies on
them for optimistic concurrency ("write only if nobody else has") is the problem
case: under drongo the guarded write always succeeds, so a test passes while the
same code can lose a write in production. `ifGenerationMatch=0`, the create-only
guard, is ignored the same way and silently overwrites.

- Scenario: `tests/fidelity/test_storage_fidelity.py::test_if_generation_match_stale_is_rejected`
- Scenario: `tests/fidelity/test_storage_fidelity.py::test_if_generation_match_zero_rejects_existing_object`
- Scenario: `tests/fidelity/test_storage_fidelity.py::test_if_metageneration_match_stale_is_rejected`

### Object listing is not paginated

`maxResults` and `pageToken` are ignored: every object comes back in a single
page. Iterating a result gives the right objects, so most tests do not notice,
but anything that depends on page boundaries (asserting a page size, threading a
page token, testing that a loop handles more than one page) sees one page where
GCS would send several.

- Scenario: `tests/fidelity/test_storage_fidelity.py::test_list_pages_honour_max_results`

## Pub/Sub

### A lapsed ack deadline does not redeliver

A pulled message stays outstanding forever. Real Pub/Sub returns it to the
backlog once `ackDeadlineSeconds` passes without an ack, which is the mechanism
behind at-least-once delivery, so a consumer that crashes mid-message is retried
in production but never retried under drongo. An explicit nack
(`modifyAckDeadline` with `0`) does redeliver, so only the timeout path is
missing.

- Scenario: `tests/fidelity/test_pubsub_fidelity.py::test_expired_ack_deadline_redelivers_the_message`
