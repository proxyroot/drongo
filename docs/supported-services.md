# Supported services

Legend: ✅ supported · 🚧 partial · ⬜ planned

## Cloud Storage (`storage`)

Client: `google-cloud-storage` · Transport: JSON API (default) · Backend: global
namespace.

| Operation | Status |
| --- | --- |
| Create / get / list / delete bucket | ✅ |
| Bucket metadata (location, labels, versioning) | 🚧 |
| Upload - simple (`media`) | ✅ |
| Upload - multipart | ✅ |
| Upload - resumable (single + chunked) | ✅ |
| Download (full) | ✅ |
| Download with `Range` | ✅ |
| Object metadata get / patch | ✅ |
| List objects (prefix + delimiter) | ✅ |
| Delete object | ✅ |
| Copy / rewrite object | ✅ |
| Bucket IAM policy (get / set / test) | ✅ |
| HMAC keys (create / list / get / update / delete) | ✅ |
| Signed URLs, object ACLs, notifications | ⬜ |

## Secret Manager (`secretmanager`)

Client: `google-cloud-secret-manager` · Transport: gRPC (default), forced to
REST during a mock scope (no code change needed) · Backend: per-project.

| Operation | Status |
| --- | --- |
| Create / get / list / delete secret | ✅ |
| Update secret (labels) | 🚧 |
| Add / get / list versions | ✅ |
| Access version (incl. `latest`) | ✅ |
| Enable / disable / destroy version | ✅ |
| IAM policy | ⬜ |

## Pub/Sub (`pubsub`)

Client: `google-cloud-pubsub` (sync, gRPC via `PUBSUB_EMULATOR_HOST`) and
`gcloud.aio.pubsub` (async, aiohttp/REST via the aiohttp interceptor) · Backend:
global namespace, shared between both transports. Use the normal clients with no
changes.

| Operation | Status |
| --- | --- |
| Create / get / list / delete topic | ✅ |
| Create / get / list / delete subscription | ✅ |
| Publish (with attributes, fan-out to all subs) | ✅ |
| Pull / acknowledge | ✅ |
| Async client (`gcloud.aio.pubsub`) | ✅ |
| Nack via `modifyAckDeadline(0)` (redelivery) | ✅ |
| Streaming pull (`subscribe()`) | ⬜ |
| Ack-deadline expiry / retention | ⬜ |
| IAM, schemas, snapshots, seek | ⬜ |

## BigQuery (`bigquery`)

Client: `google-cloud-bigquery` · Transport: REST/JSON (default) · Backend:
per-project.

| Operation | Status |
| --- | --- |
| Create / get / list / delete dataset | ✅ |
| Create / get / list / delete table (with schema) | ✅ |
| Streaming inserts (`insert_rows_json` / `insertAll`) | ✅ |
| Read rows (`list_rows` / `tabledata.list`) | ✅ |
| SQL query execution (`client.query(...)`) | ✅ (via `drongo[bigquery]`) |
| Load/extract/copy jobs, routines, views | ⬜ |

## Cloud Tasks (`cloudtasks`)

Client: `google-cloud-tasks` · Transport: gRPC (default), forced to REST during
a mock scope (no emulator env var exists) · Backend: per-project. Use the normal
client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list / delete queue | ✅ |
| Pause / resume / purge queue | ✅ |
| Create / get / list / delete task | ✅ |
| `run_task` (marks dispatched) | ✅ |
| Actual task dispatch / delivery to targets | ⬜ (no real network I/O) |
| Retry config, rate limits, IAM | ⬜ |

Note: because the client is forced onto REST, errors surface as REST-style
`google.api_core.exceptions` (e.g. a duplicate queue raises `Conflict`, not the
gRPC `AlreadyExists`). `NotFound` is the same for both.

## Cloud Run Jobs (`cloudrun`)

Client: `google-cloud-run` (`run_v2.JobsClient` / `ExecutionsClient`) · Transport:
gRPC (default), forced to REST during a mock scope · Backend: per-project. Use
the normal clients with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list / delete job | ✅ |
| `run_job` (creates an execution) | ✅ |
| Executions: get / list / delete | ✅ |
| Long-running operations (`.result()`) | ✅ (completed synchronously) |
| Actual container execution | ⬜ (no real compute) |
| Cloud Run *services* (serving), revisions, traffic | ⬜ |

Errors surface as REST-style exceptions (a duplicate job raises `Conflict`).

## Resource Manager (`resourcemanager`)

Client: `google-cloud-resource-manager` (`resourcemanager_v3.ProjectsClient`) ·
Transport: gRPC (default), forced to REST during a mock scope · Backend: global
namespace. Use the normal client with no `transport` argument. Scoped to the
Projects API.

| Operation | Status |
| --- | --- |
| Create / get project | ✅ |
| Get by `project_id` or `projects/<number>` | ✅ |
| List projects (by `parent`) | ✅ |
| Search projects | ✅ |
| Delete / undelete project | ✅ |
| Update project (display name, labels) | ✅ |
| Move project, IAM policy, tags | ⬜ |
| Folders, Organizations | ⬜ |

Mutations are long-running operations completed synchronously (`.result()`
returns immediately). A duplicate project raises `Conflict`.

## Firestore (`firestore`)

Client: `google-cloud-firestore` · Transport: gRPC (default), served by an
in-process gRPC emulator via `FIRESTORE_EMULATOR_HOST` · Backend: global
namespace. Use the normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Document set / get / update / delete | ✅ |
| `set(merge=True)`, `collection.add()` (auto id) | ✅ |
| Typed values (str/int/float/bool/null/bytes/array/map/timestamp) | ✅ |
| Subcollections | ✅ |
| Queries: `where`, `order_by`, `limit`, `offset` | ✅ |
| Composite `AND`/`OR`, `in` / `array_contains` | ✅ |
| Transactions, batched writes | ⬜ |
| Real-time listeners (`on_snapshot`) | ⬜ |
| Aggregation / collection-group queries | ⬜ |

## IAM & Service Accounts (`iam`)

Client: `google-cloud-iam` (`iam_admin_v1.IAMClient`) · Transport: gRPC only,
served by an in-process gRPC emulator with an injected transport (no REST
transport or emulator env var exists) · Backend: per-project. Use the normal
client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list / delete service account | ✅ |
| Get by email or unique id | ✅ |
| Enable / disable service account | ✅ |
| Create / list / get / delete key | ✅ |
| Update (display name / description) | ⬜ |
| Roles, IAM policy get/set | ⬜ |
| `SignBlob` / `SignJwt` | ⬜ |

## Cloud Logging (`logging`)

Client: `google-cloud-logging` (`logging.Client`) · Transport: gRPC only, served
by an in-process gRPC emulator with an injected transport · Backend: global
namespace. Use the normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Write entries (`log_text` / `log_struct` / `log_proto`) | ✅ |
| List entries (by `resource_names`) | ✅ |
| Ordering (ascending / descending) | ✅ |
| Delete a log; list logs | ✅ |
| Advanced filter language | ⬜ (entries returned unfiltered) |
| Sinks / exports, log-based metrics, tail | ⬜ |

## Cloud KMS (`kms`)

Client: `google-cloud-kms` (`kms.KeyManagementServiceClient`) · Transport: gRPC
(default), forced to REST during a mock scope · Backend: per-project. Use the
normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list key ring | ✅ |
| Create / get / list crypto key | ✅ |
| Encrypt / decrypt (with AAD) | ✅ (reversible mock, not real crypto) |
| Crypto-key versions, rotation | ⬜ |
| Asymmetric sign/verify, MAC, raw encrypt | ⬜ |
| IAM policy, import jobs | ⬜ |

## Cloud Scheduler (`cloudscheduler`)

Client: `google-cloud-scheduler` (`scheduler_v1.CloudSchedulerClient`) ·
Transport: gRPC (default), forced to REST during a mock scope · Backend:
per-project. Use the normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list / delete job | ✅ |
| Pause / resume / update | ✅ |
| `run_job` (+ executable handler) | ✅ |
| Actual cron scheduling / automatic firing | ⬜ (no real clock) |

## Cloud Functions (`cloudfunctions`)

Client: `google-cloud-functions` (`functions_v2.FunctionServiceClient`) ·
Transport: gRPC (default), forced to REST during a mock scope · Backend:
per-project. Use the normal client with no `transport` argument. Scoped to the
2nd-gen admin API.

| Operation | Status |
| --- | --- |
| Create / get / list / delete function (LRO) | ✅ |
| Update function (LRO) | ✅ |
| `generate_upload_url` | ✅ (stub) |
| Synchronous invoke | ⬜ (2nd gen has no invoke RPC) |

## Memorystore for Redis (`memorystore`)

Client: `google-cloud-redis` (`redis_v1.CloudRedisClient`) · Transport: gRPC
(default), forced to REST during a mock scope · Backend: per-project. Use the
normal client with no `transport` argument. Scoped to instance administration.

| Operation | Status |
| --- | --- |
| Create / get / list / delete instance (LRO) | ✅ |
| Update instance (LRO) | ✅ |
| Failover / export / import / upgrade | ⬜ |
| Redis data plane | ⬜ (use a real Redis) |

## Datastore (`datastore`)

Client: `google-cloud-datastore` (`datastore.Client`) · Transport: gRPC (default),
served by an in-process gRPC emulator via `DATASTORE_EMULATOR_HOST` · Backend:
per-project. Use the normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| put / get / delete (`Commit` / `Lookup`) | ✅ |
| Named + auto-id keys (`AllocateIds`) | ✅ |
| Typed values (str/int/float/bool/null/bytes/array/timestamp/key) | ✅ |
| Queries: kind, filters, order, limit, offset | ✅ |
| Composite `AND`/`OR`, `IN`/`NOT_IN` | ✅ |
| Transactions (accepted, completed synchronously) | ✅ |
| Ancestor queries, projections, cursors, aggregation | ⬜ |

## Bigtable (`bigtable`)

Client: `google-cloud-bigtable` (`bigtable.Client`) · Transport: gRPC (default),
served by an in-process gRPC emulator via `BIGTABLE_EMULATOR_HOST` · Backend:
per-project. Use the normal client with `admin=True`.

| Operation | Status |
| --- | --- |
| Create / get / list / delete table, modify families | ✅ |
| `set_cell`, versioned cells, deletes | ✅ |
| `read_row`, `read_rows` (ranges, limit) | ✅ |
| Batch `mutate_rows`, `sample_row_keys` | ✅ |
| Read filters, `check_and_mutate_row` | ⬜ |
| Instance admin, change streams, aggregations | ⬜ |

## Planned

Cloud Spanner · Firestore transactions & listeners · IAM roles & policies · KMS
key versions · Bigtable read filters. See the
[roadmap](https://drongo.proxyroot.com/roadmap/) and
[open a service request](https://github.com/proxyroot/drongo/issues/new/choose).
