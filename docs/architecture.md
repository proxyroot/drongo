# Architecture

`drongo` deliberately mirrors [`moto`](https://github.com/getmoto/moto), adapted
from AWS/botocore to GCP's REST + JSON (and gRPC-over-REST) APIs.

## The big picture

```
your test code
      │  google-cloud-python client (requests / AuthorizedSession)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  mock_gcp scope                                              │
│                                                             │
│  responses (HTTP interception)  ──►  BaseResponse.dispatch  │
│  google.auth.default patched         (per service)          │
│                                            │                │
│                                            ▼                │
│                                     BackendDict[project]    │
│                                     └─ BaseBackend (state)  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### `mock_gcp` and the controller (`core/decorator.py`)

`mock_gcp` returns a `DrongoMock` that drives a process-wide, **reentrant**
`DrongoController`. On the outermost `start()` it:

1. resets every backend to empty state,
2. starts a [`responses`](https://github.com/getsentry/responses) mock and
   registers every service's routes on it, and
3. patches `google.auth.default` to hand back `AnonymousCredentials` plus a
   default project (see `core/credentials.py`), so client construction never
   touches the metadata server or an OAuth endpoint.

Nested scopes share state and only reset at the outermost boundary - the same
semantics as nested `mock_aws`.

### Interception via `responses`

The google client libraries send REST traffic through
`google.auth.transport.requests.AuthorizedSession`, a `requests.Session`
subclass. `responses` patches `requests`, so registering broad per-host
callbacks lets `drongo` serve every call from memory - no sockets. This is the GCP
analogue of moto's botocore stubber.

### Emulators for gRPC (`core/emulator.py`)

gRPC cannot be intercepted the `responses` way: `grpcio` is a compiled HTTP/2
stack with no pure-Python seam to patch, and payloads are binary Protobuf over
multiplexed streams. So gRPC-first services (Pub/Sub) implement a
`BaseEmulator`: `mock_gcp` starts a real in-process gRPC server backed by the
service's `models.py` and points the client at it via the standard
`PUBSUB_EMULATOR_HOST` env var, exactly how Google's own emulators work. The
client uses its default transport with no code change. The Pub/Sub server is
built from generic gRPC handlers using the client library's own proto-plus
(de)serializers, so no generated servicer classes are needed, and it is created
once and reused across scopes (state is reset between scopes).

A service provides an HTTP `response` router, a gRPC `emulator`, or both; the
controller wires up whichever are present.

### `BaseResponse` (`core/responses.py`)

Each service subclasses `BaseResponse` and implements one method per API call.
Routing comes from the service's `urls.py`:

- `url_bases` - regexes matching `scheme://host`.
- `url_paths` - maps `"<METHOD> <path-regex>"` to a handler.

`dispatch` decodes the incoming `PreparedRequest` into a `Request`, matches a
route, and calls the handler. The very same `handle()` method powers the
standalone server.

### `BaseBackend` and `BackendDict` (`core/backend.py`)

moto keys backends by `account_id` **and** `region`; GCP's natural shard key is
the **project**, so `BackendDict` maps `project -> backend`. Services with a
global resource namespace (Cloud Storage buckets, like S3) set
`global_namespace=True` so every project shares one backend.

Inspect state via `get_backend("storage")["my-project"]`.

### Standalone server (`server.py`)

A stdlib `ThreadingHTTPServer` decodes each request into the same `Request`
object and asks each service's `BaseResponse.handle` in turn. Because it reuses
the route tables, the server and in-process modes never drift.

## Directory layout

```
src/drongo/
├── __init__.py            # public API: mock_gcp, get_backend, __version__
├── backends.py            # moto-style get_backend accessor
├── cli.py                 # `drongo` CLI (server, services)
├── server.py              # standalone HTTP server
├── pytest_plugin.py       # the `drongo` fixture
├── core/
│   ├── backend.py         # BaseBackend, BackendDict
│   ├── responses.py       # BaseResponse, Request, dispatch (HTTP)
│   ├── emulator.py        # BaseEmulator (gRPC in-process servers)
│   ├── registry.py        # ServiceDefinition + get_backend
│   ├── decorator.py       # mock_gcp + controller
│   ├── credentials.py     # anonymous-credential patching
│   ├── exceptions.py      # GCP JSON error envelope
│   └── utils.py           # timestamps, checksums
└── services/
    ├── storage/           # models.py + responses.py + urls.py
    ├── secretmanager/     # models.py + responses.py + urls.py
    └── pubsub/            # models.py + emulator.py (gRPC)
```
