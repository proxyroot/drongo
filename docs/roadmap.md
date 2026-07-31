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
| BigQuery | REST interception | datasets, tables, streaming inserts, read rows, SQL query execution (via `drongo[bigquery]`) |
| Cloud Tasks | forced REST | queues, tasks, run/dispatch handlers, pause/resume/purge |
| Cloud Run Jobs | forced REST (LRO) | jobs, executions, `run_job` handlers |
| Resource Manager | forced REST (LRO) | projects CRUD, search, undelete |
| Firestore | in-process gRPC emulator | documents, subcollections, typed values, queries |
| Datastore | in-process gRPC emulator | entities, keys, typed values, filtered/ordered queries |
| IAM & Service Accounts | injected gRPC transport | service accounts + keys |
| Cloud Logging | injected gRPC transport | write/list log entries, delete/list logs |
| Cloud KMS | forced REST | key rings, crypto keys, encrypt/decrypt |
| Cloud Scheduler | forced REST | cron jobs, pause/resume, `run_job` handlers |
| Cloud Functions | forced REST (LRO) | 2nd-gen deploy/manage functions |
| Memorystore (Redis) | forced REST (LRO) | instance admin |
| Vertex AI | forced REST (LRO) | datasets, endpoints, models, custom/batch jobs (control plane) |

## Available capabilities

- ✅ **One decorator / fixture** (`@mock_gcp`, `drongo` pytest fixture, context manager, class decorator)
- ✅ **Transparent transports** (REST interception, gRPC emulators, forced-REST) so default clients work unchanged
- ✅ **Executable handlers** — run real Python when a job runs, a task dispatches, or a message publishes
- ✅ **Faker data seeding** (`drongo.seed`)
- ✅ **Standalone HTTP server** (`drongo server`) for non-Python SDKs
- ✅ **Typed** (`py.typed`, mypy-checked)

## Planned services

### Next up — prioritized

These are the next services to build, ahead of the tiers below.

| Service | Client | Notes |
| --- | --- | --- |
| Cloud Monitoring | `google-cloud-monitoring` | metric descriptors, time series write/list, alert policies |
| Document AI | `google-cloud-documentai` | processors, process / batch-process documents |
| Artifact Registry | `google-cloud-artifact-registry` | repositories, packages, versions, tags |
| Storage Transfer | `google-cloud-storage-transfer` | transfer jobs and operations (control plane) |

### Tier 1 — shipped

Tier 1 is done: Cloud Logging, Cloud KMS, IAM & Service Accounts, Cloud
Scheduler, Cloud Functions, Datastore, and Memorystore are all available (see the
table above). The one item still open is:

| Service | Client | Notes |
| --- | --- | --- |
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

Dataflow · Dataproc · Vision / Speech / Translation / Natural Language · GKE
(Container) · Cloud Build · Cloud DNS · Eventarc · Workflows · Cloud Trace.

(Cloud Monitoring and Artifact Registry are promoted to
[Next up](#next-up-prioritized).)

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
- 🚧 **Deepen existing services** — e.g. Pub/Sub streaming pull, Firestore
  transactions & real-time listeners, Cloud Tasks retry semantics, Storage
  ACLs/IAM.

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
