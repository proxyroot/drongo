# Verifying drongo against real GCP

drongo's mocks are written by hand from the API docs. That leaves one question a
normal test suite cannot answer: does a mocked call behave the way the real
service does? Without an answer, a test can pass under `@mock_gcp` and the same
code can fail in production.

The suite in `tests/fidelity/` answers it for the behaviour it covers. Each
scenario is written to run **unchanged** against two targets:

- **the mock**, by default, so pull-request CI needs no credentials;
- **real GCP**, when you opt in, using Application Default Credentials.

A scenario is adjusted until it passes against real GCP, so its assertions
record how GCP actually behaves rather than how the docs read. drongo is then
held to the same test. This is the approach moto takes with `@aws_verified`, and
the one AWS describes for its own emulator.

!!! note

    This is a maintainer tool, not something you need to run to use drongo.
    `pytest` covers it under the mock like any other test.

## Running it

Against the mock, which is what CI does:

```bash
pytest tests/fidelity
```

Against real GCP:

```bash
gcloud auth application-default login
export DRONGO_TEST_ALLOW_GCP_REQUEST=true
export DRONGO_TEST_PROJECT=my-sandbox-project
pytest tests/fidelity -v
```

Both variables are required. `DRONGO_TEST_PROJECT` has no default on purpose:
creating buckets and topics in whatever project your ambient credentials happen
to point at is exactly the accident worth preventing. The header of every run
says which target is active, so a run is never ambiguous:

```
drongo fidelity: LIVE against project 'my-sandbox-project'
```

To select the suite from anywhere in the repo, use the marker:

```bash
pytest -m gcp_verified
```

!!! warning "A live run creates real, billable resources"

    Use a sandbox project with a budget alert, not a shared or production one.
    The resources are small and short-lived (a few buckets, objects, topics and
    subscriptions), but they are real.

## How a live run avoids leaking resources

Every resource a scenario creates is:

1. **named** `drongo-fid-<run id>-<slug>`, with a fresh run id per session.
   Bucket names are a global namespace, so this has to be unique per run rather
   than per project;
2. **labelled** `drongo-fidelity=<run id>`;
3. **registered** with a per-test ledger that deletes in reverse creation order,
   so a subscription goes before its topic and objects before their bucket.

Teardown runs whether the test passed or failed. A test that crashes the process
cannot run its own deleter, so an end-of-session sweep also deletes anything
carrying the run's prefix. If cleanup still fails, the run fails loudly with the
names to delete by hand rather than leaving them silently behind.

## Writing a scenario

```python
from . import gcp_verified


@gcp_verified
def test_deleting_non_empty_bucket_conflicts(bucket):
    bucket.blob("obj.txt").upload_from_string("payload")

    with pytest.raises(gexc.Conflict):
        bucket.delete()
```

`@gcp_verified` requests the `gcp_target` fixture, which either activates
`mock_gcp` or points the test at `DRONGO_TEST_PROJECT`. The `bucket`, `topic`
and `subscription` fixtures build correctly named and labelled resources on
whichever target is live.

Two rules keep a scenario able to pass on both targets:

**Assert on behaviour, not on values.** Status codes (through the
`google.api_core` exception they map to), state transitions, which fields the
server fills in. Never etags, timestamps, or the generation number itself: real
GCS generations are microsecond timestamps and drongo's are a counter, so
`new > old` is a fact about both while `new == 2` is a fact about neither.

**Never branch on the target.** A body that reads `if live:` is two tests
pretending to be one, and the mock half stops being evidence of anything. Test
plumbing may differ (waiting out a real ack deadline is meaningless against a
mock with no clock), but assertions may not.

Resources are shared in a real project, so prefer membership over equality:
`assert topic in listed`, not `assert listed == [topic]`. Another run, or
another engineer, may own the rest.

## When drongo diverges

If a scenario passes against GCP but fails under the mock, that is a finding,
not a broken test. Mark it and write it up:

```python
@gcp_verified
@known_gap("drongo ignores ifGenerationMatch, so a stale write is not rejected")
def test_if_generation_match_stale_is_rejected(bucket):
    blob = bucket.blob("obj")
    blob.upload_from_string("v1")
    stale = blob.generation
    blob.upload_from_string("v2")

    with pytest.raises(gexc.PreconditionFailed):
        blob.upload_from_string("v3", if_generation_match=stale)
```

`known_gap` is `xfail(strict=True)` under the mock and inert on a live run,
where the behaviour is GCP's own. Strict matters: when someone closes the gap,
the scenario starts **failing** as an unexpected pass, which forces the marker
off. A fixed gap cannot stay on the list, and
[`KNOWN_GAPS.md`](https://github.com/proxyroot/drongo/blob/main/KNOWN_GAPS.md)
cannot drift from the suite, because `test_known_gaps_doc.py` compares the two
and fails if they disagree.

That is the point of the whole arrangement: divergence from GCP is written down
and visible, instead of being discovered in production.

## Coverage

The suite covers Cloud Storage and Pub/Sub today, chosen because they are the
most widely used services and the cheapest to exercise live. Extending it
service by service, recording live responses so CI can replay them, and
generating a per-operation coverage matrix from Google's Discovery documents and
protos are tracked on the [roadmap](roadmap.md).
