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

Client: `google-cloud-secret-manager` · Transport: REST (`transport="rest"`) ·
Backend: per-project.

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

## Planned

Cloud Tasks · Firestore · Resource Manager · data seeding with Faker. See the
[roadmap](../README.md#roadmap) and
[open a service request](https://github.com/proxyroot/drongo/issues/new/choose).
