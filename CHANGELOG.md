# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-28

### Added

- Initial release. 🐱
- `mock_gcp` - mock every supported GCP service, usable as a bare decorator, a
  called decorator, a context manager, a class decorator, and a
  `unittest.TestCase` mixin. Scopes are reentrant.
- **Cloud Storage** mock (JSON API): buckets, objects, simple/multipart/resumable
  uploads, downloads with `Range` support, listing with prefix + delimiter,
  copy/rewrite, and metadata updates.
- **Secret Manager** mock (REST transport): secrets, versions, access, and
  enable/disable/destroy.
- **Standalone server** (`gato server`) replaying the same route tables over a
  real socket, for use with emulator env vars or non-Python SDKs.
- **pytest plugin** exposing a `gato` fixture (auto-registered on install).
- Project-keyed `BackendDict` and `get_backend()` for inspecting state, mirroring
  moto's internals.

[Unreleased]: https://github.com/proxyroot/gato/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/proxyroot/gato/releases/tag/v0.1.0
