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

## Planned

Pub/Sub · Firestore · BigQuery · Cloud Tasks · Resource Manager. See the
[roadmap](../README.md#roadmap) and
[open a service request](https://github.com/proxyroot/gato/issues/new/choose).
