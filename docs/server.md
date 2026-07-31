# Standalone server

For most Python tests you want the `@mock_gcp` decorator, which patches the
clients in-process. But sometimes you need a real HTTP endpoint:

- your SDK is in another language (Go, Node, Java, ...),
- you run the google clients in **emulator mode** (pointed at an env var),
- you want a long-lived fake shared across processes.

`drongo server` is the same trick as `moto_server`: it replays drongo's HTTP
route tables over a real socket.

## Starting the server

```bash
drongo server --port 9090
```

Then point the relevant emulator env var at it. For Cloud Storage:

```bash
export STORAGE_EMULATOR_HOST=http://localhost:9090
```

```python
from google.cloud import storage
from google.auth.credentials import AnonymousCredentials

client = storage.Client(project="p", credentials=AnonymousCredentials())
client.create_bucket("b")  # served by the drongo server over HTTP
```

## Emulator env vars

Each google-cloud client honors a service-specific env var that points it at an
alternative host. Set the one for the service you are testing and the client
sends its requests to drongo instead of Google:

| Service | Env var |
| --- | --- |
| Cloud Storage | `STORAGE_EMULATOR_HOST` |
| Pub/Sub | `PUBSUB_EMULATOR_HOST` |
| BigQuery | `BIGQUERY_EMULATOR_HOST` |

When you use the in-process `@mock_gcp` decorator instead, drongo sets and clears
these for you where needed (for example, it runs the Pub/Sub gRPC emulator and
sets `PUBSUB_EMULATOR_HOST` automatically).

## Non-Python SDKs

Because the server speaks the real REST/JSON API, any language's SDK can point at
it the same way. This is what makes drongo usable from a polyglot test suite or
a docker-compose stack, not just Python.

## Management API

The server exposes a small management API (drongo's analogue of moto's
`/moto-api`), handy for long-lived servers and non-Python test suites:

| Route | Does |
| --- | --- |
| `POST /drongo/reset` | Clears **every** service's in-memory state |
| `GET /drongo/health` | Reports liveness and the registered services |

```bash
drongo server --port 9090 &

# Between tests, reset all state over HTTP (from any language):
curl -X POST http://localhost:9090/drongo/reset
# -> {"reset": true}

curl http://localhost:9090/drongo/health
# -> {"status": "ok", "services": ["bigquery", "storage", ...]}
```

For in-process Python tests you rarely need this - `@mock_gcp` and the `drongo`
fixture already reset state between tests. The endpoint matters when the server
is shared across processes or driven from another language.

## When to use which

| | `@mock_gcp` (in-process) | `drongo server` (HTTP) |
| --- | --- | --- |
| Python unit tests | Best choice | Overkill |
| Other-language SDKs | Not possible | Best choice |
| Cross-process / shared state | No | Yes |
| Speed | Fastest (no sockets) | Fast (local socket) |
| Setup | One decorator | Start a process + env var |
