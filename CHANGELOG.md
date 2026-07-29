# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Fake data generators** (`drongo.seed`, optional `drongo[faker]`): populate the
  mocked services with realistic Faker data. `seed.bigquery_rows` (typed by
  schema), `seed.storage_blobs`, and `seed.pubsub_messages`, with `overrides` and
  reproducible `seed.seed(n)`.
- **Cloud Run Jobs** mock. gRPC-first with no emulator env var, so served over
  REST with the client forced onto its REST transport. Covers jobs CRUD,
  `run_job`, and executions get/list/delete. Long-running operations are
  completed synchronously (each mutation returns a done `Operation`).
- **Secret Manager** now works with the default client (no `transport="rest"`
  needed): drongo forces it onto its REST transport during a mock scope.

### Fixed

- Storage: a `multipart/related` upload whose payload is itself JSON no longer
  fails with "Cannot determine object name" (the parser now assigns parts by
  position instead of by `Content-Type`).

## [0.2.0] - 2026-07-29

### Added

- Versioning is now derived from the git tag via `hatch-vcs` (tag `vX.Y.Z` builds
  `X.Y.Z`); no manual version bumps.
- **Cloud Tasks** mock. Cloud Tasks is gRPC-first with no emulator env var, so
  drongo serves it over REST and transparently forces the client onto its REST
  transport during a mock scope (a new `patchers` mechanism on the service
  registry). Covers queues and tasks CRUD, `run_task`, purge, and pause/resume.
- **BigQuery** mock (REST/JSON). Datasets, tables (with schema), streaming
  inserts (`insertAll`), reading rows back (`tabledata.list`), and list/delete.
  SQL query execution is out of scope (it needs a SQL engine).
- **Pub/Sub** mock. Pub/Sub is gRPC-first, so drongo runs an in-process gRPC
  emulator (redirected via `PUBSUB_EMULATOR_HOST`) backed by the same in-memory
  model layer as the HTTP services. The normal (default-transport) client works
  with no code change. Covers topics, subscriptions, publish fan-out, pull,
  acknowledge, and nack via `modifyAckDeadline(0)`.
- Core `BaseEmulator` abstraction so gRPC-first services can be mocked alongside
  the HTTP interception layer; `ServiceDefinition` now accepts an `emulator`.

### Fixed

- Standalone server skips services with no HTTP router (gRPC-only services)
  instead of raising.

## [0.1.0] - 2026-07-28

### Added

- Initial release. 🐦
- `mock_gcp` - mock every supported GCP service, usable as a bare decorator, a
  called decorator, a context manager, a class decorator, and a
  `unittest.TestCase` mixin. Scopes are reentrant.
- **Cloud Storage** mock (JSON API): buckets, objects, simple/multipart/resumable
  uploads, downloads with `Range` support, listing with prefix + delimiter,
  copy/rewrite, and metadata updates.
- **Secret Manager** mock (REST transport): secrets, versions, access, and
  enable/disable/destroy.
- **Standalone server** (`drongo server`) replaying the same route tables over a
  real socket, for use with emulator env vars or non-Python SDKs.
- **pytest plugin** exposing a `drongo` fixture (auto-registered on install).
- Project-keyed `BackendDict` and `get_backend()` for inspecting state, mirroring
  moto's internals.

[Unreleased]: https://github.com/proxyroot/drongo/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/proxyroot/drongo/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/proxyroot/drongo/releases/tag/v0.1.0
