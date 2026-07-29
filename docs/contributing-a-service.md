# Adding a service

Adding a GCP service to `drongo` is intentionally mechanical - the same shape moto
uses. A service lives in `src/drongo/services/<name>/` and is three files plus an
`__init__.py`.

We'll sketch a fictional `widgets` service. Use the existing `storage` and
`secretmanager` services as real references.

## 1. `models.py` - in-memory state

```python
from drongo.core.backend import BaseBackend, BackendDict


class WidgetsBackend(BaseBackend):
    def setup(self) -> None:
        # Called on creation and on every reset. Initialise empty state.
        self.widgets: dict[str, dict] = {}

    def create_widget(self, name: str) -> dict:
        widget = {"name": f"projects/{self.project}/widgets/{name}"}
        self.widgets[name] = widget
        return widget


widgets_backends: BackendDict[WidgetsBackend] = BackendDict(WidgetsBackend, "widgets")
```

- Backends are **project-scoped**: `self.project` is set for you.
- Use `global_namespace=True` if the resource namespace is global (like GCS
  buckets), so every project shares one backend.

## 2. `responses.py` - request handlers

```python
from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.widgets.models import widgets_backends


class WidgetsResponse(BaseResponse):
    def backend_for(self, request: Request) -> "WidgetsBackend":
        return widgets_backends[request.path_params["project"]]

    def create_widget(self, request: Request) -> HttpResponse:
        widget = self.backend_for(request).create_widget(request.param("widgetId"))
        return json_response(widget)
```

Handlers receive a decoded `Request` (`.path_params`, `.param()`, `.header()`,
`.json()`, `.body`) and return `(status, headers, body)` - use `json_response`
for JSON. Raise `drongo.core.exceptions.not_found(...)` etc. for errors; they're
serialized into the GCP error envelope automatically.

## 3. `urls.py` - routing

```python
from drongo.services.widgets.responses import WidgetsResponse

url_bases = [r"https?://widgets\.googleapis\.com"]

url_paths = {
    r"POST /v1/projects/(?P<project>[^/]+)/widgets": WidgetsResponse.create_widget,
    r"GET /v1/projects/(?P<project>[^/]+)/widgets/(?P<widget>[^/]+)": (
        WidgetsResponse.get_widget
    ),
}
```

- Keys are `"<METHOD> <path-regex>"`; the regex is `fullmatch`ed against the URL
  path. Named groups land in `request.path_params`.
- **Order matters** - list more specific paths first.

## 4. `__init__.py` - register the service

```python
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.widgets import urls
from drongo.services.widgets.models import widgets_backends
from drongo.services.widgets.responses import WidgetsResponse

register_service(
    ServiceDefinition(
        name="widgets",
        backends=widgets_backends,
        response=WidgetsResponse(urls.url_bases, urls.url_paths),
    )
)
```

Finally, import your package in `src/drongo/services/__init__.py` so it registers
on load.

## 5. Tests

Add tests under `tests/<name>/` that drive the **real** google-cloud client
through `mock_gcp` (or the `drongo` fixture). Assert on client-observable behavior
first, and optionally on raw backend state via
`get_backend("widgets")["project"]`.

## Tips

- Find the exact URLs/JSON shapes by capturing a request: register a `responses`
  callback and print `request.url` / `request.body` (see how the storage
  multipart parser was reverse-engineered).
- Get the **HTTP status codes** right - the client maps them to
  `google.api_core.exceptions` subclasses.
- Run `make check` before opening a PR.
