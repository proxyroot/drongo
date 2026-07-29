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
| Signed URLs, ACLs, IAM, notifications | ⬜ |

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

Client: `google-cloud-pubsub` · Transport: gRPC (default), served by an
in-process gRPC emulator via `PUBSUB_EMULATOR_HOST` · Backend: global namespace.
Use the normal client with no `transport` argument.

| Operation | Status |
| --- | --- |
| Create / get / list / delete topic | ✅ |
| Create / get / list / delete subscription | ✅ |
| Publish (with attributes, fan-out to all subs) | ✅ |
| Pull / acknowledge | ✅ |
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
| SQL query execution (`client.query(...)`) | ⬜ (needs a SQL engine) |
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

## Planned

Cloud Logging · Firestore transactions & listeners · Folders/Organizations. See the
[roadmap](https://github.com/proxyroot/drongo#roadmap) and
[open a service request](https://github.com/proxyroot/drongo/issues/new/choose).
