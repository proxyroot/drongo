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

> gRPC-only calls are not intercepted yet. Services whose clients default to
> gRPC (Secret Manager, Pub/Sub, …) are used with `transport="rest"`.

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
│   ├── responses.py       # BaseResponse, Request, dispatch
│   ├── registry.py        # ServiceDefinition + get_backend
│   ├── decorator.py       # mock_gcp + controller
│   ├── credentials.py     # anonymous-credential patching
│   ├── exceptions.py      # GCP JSON error envelope
│   └── utils.py           # timestamps, checksums
└── services/
    ├── storage/           # models.py + responses.py + urls.py
    └── secretmanager/     # models.py + responses.py + urls.py
```
