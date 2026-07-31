"""HTTP handlers implementing the Document AI REST (v1) API.

Document AI's client is gRPC-first; drongo forces it onto REST during a mock
scope (see ``__init__.py``). Processor create is synchronous; enable / disable /
delete and batch-process are long-running operations completed synchronously
here. ``process`` runs a registered handler (see ``models.py``).
"""

from __future__ import annotations

import base64
from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.documentai.models import DocumentAIBackend, documentai_backends

_PREFIX = "type.googleapis.com/google.cloud.documentai.v1."
EMPTY_TYPE = "type.googleapis.com/google.protobuf.Empty"
ENABLE_TYPE = _PREFIX + "EnableProcessorResponse"
DISABLE_TYPE = _PREFIX + "DisableProcessorResponse"
BATCH_TYPE = _PREFIX + "BatchProcessResponse"

# A couple of the server-defined processor types, for discovery flows.
_BUILTIN_TYPES = [
    {"type": "OCR_PROCESSOR", "category": "GENERAL"},
    {"type": "FORM_PARSER_PROCESSOR", "category": "GENERAL"},
]


class DocumentAIResponse(BaseResponse):
    """Handles Document AI REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> DocumentAIBackend:
        return documentai_backends[request.path_params["project"]]

    def _parent(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _processor(self, request: Request) -> str:
        return f"{self._parent(request)}/processors/{request.path_params['processor']}"

    def _process_target(self, request: Request) -> str:
        name = self._processor(request)
        version = request.path_params.get("version")
        return f"{name}/processorVersions/{version}" if version else name

    # -- processors --------------------------------------------------------

    def create_processor(self, request: Request) -> HttpResponse:
        processor = self.backend_for(request).create_processor(
            self._parent(request), request.json()
        )
        return json_response(processor)

    def get_processor(self, request: Request) -> HttpResponse:
        return json_response(
            self.backend_for(request).get_processor(self._processor(request))
        )

    def list_processors(self, request: Request) -> HttpResponse:
        processors = self.backend_for(request).list_processors(self._parent(request))
        return json_response({"processors": processors})

    def delete_processor(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.delete_processor(self._processor(request))
        return json_response(
            backend.operation(self._parent(request), {"@type": EMPTY_TYPE})
        )

    def enable_processor(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.set_state(self._processor(request), "ENABLED")
        return json_response(
            backend.operation(self._parent(request), {"@type": ENABLE_TYPE})
        )

    def disable_processor(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        backend.set_state(self._processor(request), "DISABLED")
        return json_response(
            backend.operation(self._parent(request), {"@type": DISABLE_TYPE})
        )

    # -- processing --------------------------------------------------------

    def process_document(self, request: Request) -> HttpResponse:
        body = request.json()
        raw = body.get("rawDocument") or {}
        inline = body.get("inlineDocument") or {}
        content = base64.b64decode(raw["content"]) if raw.get("content") else b""
        mime_type = raw.get("mimeType") or inline.get("mimeType") or ""
        document = self.backend_for(request).process(
            self._process_target(request), content, mime_type
        )
        return json_response(
            {"document": document, "humanReviewStatus": {"state": "SKIPPED"}}
        )

    def batch_process(self, request: Request) -> HttpResponse:
        backend = self.backend_for(request)
        return json_response(
            backend.operation(self._parent(request), {"@type": BATCH_TYPE})
        )

    # -- processor types ---------------------------------------------------

    def fetch_processor_types(self, request: Request) -> HttpResponse:
        return json_response({"processorTypes": self._processor_types(request)})

    def list_processor_types(self, request: Request) -> HttpResponse:
        return json_response({"processorTypes": self._processor_types(request)})

    def get_processor_type(self, request: Request) -> HttpResponse:
        p = request.path_params
        name = f"{self._parent(request)}/processorTypes/{p['type']}"
        return json_response({"name": name, "type": p["type"], "category": "GENERAL"})

    def _processor_types(self, request: Request) -> list[dict[str, Any]]:
        parent = self._parent(request)
        return [
            {"name": f"{parent}/processorTypes/{t['type']}", **t}
            for t in _BUILTIN_TYPES
        ]

    # -- operations (LRO polling) ------------------------------------------

    def get_operation(self, request: Request) -> HttpResponse:
        name = f"{self._parent(request)}/operations/{request.path_params['operation']}"
        return json_response(self.backend_for(request).get_operation(name))
