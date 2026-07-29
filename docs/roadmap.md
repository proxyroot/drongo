# Roadmap

Where drongo is and where it's going. Priorities are driven by how often a
service is mocked in tests and how feasible the mock is, informed by how
[moto](https://github.com/getmoto/moto) has grown its AWS coverage.

Legend: ✅ available · 🚧 partial · ⬜ planned

## Available services

| Service | Transport strategy | Depth |
| --- | --- | --- |
| Cloud Storage | REST interception | buckets, objects, uploads (simple/multipart/resumable), ranged downloads, list, copy/rewrite |
| Secret Manager | forced REST | secrets, versions, access, enable/disable/destroy |
| Pub/Sub | in-process gRPC emulator | topics, subscriptions, publish fan-out, pull/ack/nack, push handlers |
| BigQuery | REST interception | datasets, tables, streaming inserts, read rows (no SQL engine) |
| Cloud Tasks | forced REST | queues, tasks, run/dispatch handlers, pause/resume/purge |
| Cloud Run Jobs | forced REST (LRO) | jobs, executions, `run_job` handlers |
| Resource Manager | forced REST (LRO) | projects CRUD, search, undelete |
| Firestore | in-process gRPC emulator | documents, subcollections, typed values, queries |

## Available capabilities

- ✅ **One decorator / fixture** (`@mock_gcp`, `drongo` pytest fixture, context manager, class decorator)
- ✅ **Transparent transports** (REST interception, gRPC emulators, forced-REST) so default clients work unchanged
- ✅ **Executable handlers** — run real Python when a job runs, a task dispatches, or a message publishes
- ✅ **Faker data seeding** (`drongo.seed`)
- ✅ **Standalone HTTP server** (`drongo server`) for non-Python SDKs
- ✅ **Typed** (`py.typed`, mypy-checked)

## Planned services

### Tier 1 — next up (high test-demand, feasible)

| Service | Client | Notes |
| --- | --- | --- |
| Cloud Logging | `google-cloud-logging` | write/list log entries; common in almost every app |
| Cloud KMS | `google-cloud-kms` | key rings/keys, encrypt/decrypt/sign (forced REST) |
| IAM & Service Accounts | `google-cloud-iam` | service accounts + keys; complements Resource Manager |
| Cloud Scheduler | `google-cloud-scheduler` | cron jobs; pairs with executable handlers |
| Cloud Functions | `google-cloud-functions` | functions CRUD + `call` (executable handler, LRO) |
| Datastore mode | `google-cloud-datastore` | reuse the Firestore document store |
| Storage depth | `google-cloud-storage` | signed URLs, IAM, notifications, HMAC keys |

### Tier 2 — databases & infrastructure

| Service | Client | Notes |
| --- | --- | --- |
| Cloud Spanner | `google-cloud-spanner` | instances, databases, sessions, mutations (gRPC emulator) |
| Cloud Bigtable | `google-cloud-bigtable` | instances, tables, row read/write (gRPC emulator) |
| Memorystore (Redis) | `google-cloud-redis` | instance admin (forced REST, LRO) |
| Cloud SQL Admin | discovery API | instance/database admin (control plane only) |
| Compute Engine | `google-cloud-compute` | instances, disks, networks, firewalls (REST; large) |

### Tier 3 — analytics, ML, platform

Dataflow · Dataproc · Vertex AI · Vision / Speech / Translation / Natural
Language · GKE (Container) · Cloud Build · Artifact Registry · Cloud DNS ·
Eventarc · Workflows · Cloud Monitoring · Cloud Trace.

## Planned capabilities

Informed by moto's management plane and coverage tracking:

- ⬜ **Coverage matrix** — a per-operation status doc for every service (moto's
  `IMPLEMENTATION_COVERAGE.md` is the model), so gaps are explicit.
- ⬜ **Management endpoint in server mode** — an HTTP reset/seed/config route
  (à la moto's `/moto-api/reset`) for cross-process and non-Python test suites.
- ⬜ **State-transition manager** — let resources advance over time/calls
  (LRO progress, a Cloud Run execution going `running` → `succeeded`, a Compute
  instance `provisioning` → `running`) instead of completing instantly.
- ⬜ **Deterministic resource-id seeding** — reproducible generated ids, the
  data-seeding counterpart drongo already has for field values.
- 🚧 **Deepen existing services** — e.g. BigQuery query execution, Pub/Sub
  streaming pull, Firestore transactions & real-time listeners, Cloud Tasks
  retry semantics, Storage ACLs/IAM.

## Relationship to moto

drongo deliberately mirrors moto's architecture (per-service
`models.py`/`responses.py`/`urls.py`, a project-keyed `BackendDict`, a standalone
server) and adapts it to GCP: where AWS is uniformly HTTP and moto intercepts
botocore with a single stubber, GCP is gRPC-first for many services, so drongo
adds in-process **gRPC emulators** and **forced-REST** transport patching
alongside HTTP interception. moto executes some workloads via Docker (Lambda);
drongo runs them **in-process** via executable handlers.

Want a service sooner? [Open an issue](https://github.com/proxyroot/drongo/issues/new/choose)
or [contribute it](contributing-a-service.md) — adding one is intentionally mechanical.
