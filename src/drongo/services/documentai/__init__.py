"""Google Cloud Document AI mock.

Document AI defaults to gRPC but ships a REST transport and has no emulator env
var, so drongo forces the client onto REST during a mock scope and serves it from
the HTTP layer. The user's default client works unchanged.

Scoped to processors (CRUD + enable/disable), document processing via a handler,
batch processing, and processor-type discovery.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.patching import force_rest_patchers
from drongo.core.registry import ServiceDefinition, register_service
from drongo.services.documentai import urls
from drongo.services.documentai.models import (
    DocumentAIBackend,
    ProcessorHandler,
    documentai_backends,
)
from drongo.services.documentai.responses import DocumentAIResponse

__all__ = [
    "DocumentAIBackend",
    "DocumentAIResponse",
    "documentai_backends",
    "processor_handler",
    "register_processor_handler",
]


def _project(processor_name: str) -> str:
    parts = processor_name.split("/")
    if len(parts) < 6 or parts[0] != "projects" or parts[4] != "processors":
        raise ValueError(
            "Expected a processor resource name like "
            "'projects/<p>/locations/<l>/processors/<id>', got: " + repr(processor_name)
        )
    return parts[1]


def register_processor_handler(processor_name: str, handler: ProcessorHandler) -> None:
    """Bind a callable to a processor so ``process_document`` runs it.

    The handler receives ``(content, mime_type)`` and returns the resulting
    Document as a proto-JSON dict. ``processor_name`` is the full resource name
    (``projects/<p>/locations/<l>/processors/<id>``). Call this inside an active
    ``mock_gcp`` scope; the binding is cleared when the scope resets.
    """
    documentai_backends[_project(processor_name)].register_processor_handler(
        processor_name, handler
    )


def processor_handler(
    processor_name: str,
) -> Callable[[ProcessorHandler], ProcessorHandler]:
    """Decorator form of :func:`register_processor_handler`.

    ::

        @documentai.processor_handler("projects/p/locations/us/processors/abc")
        def extract(content, mime_type):
            return {"text": content.decode(), "entities": [...]}
    """

    def decorator(handler: ProcessorHandler) -> ProcessorHandler:
        register_processor_handler(processor_name, handler)
        return handler

    return decorator


def _patchers() -> list[Any]:
    return force_rest_patchers(
        [("google.cloud.documentai_v1", "DocumentProcessorServiceClient")]
    )


register_service(
    ServiceDefinition(
        name="documentai",
        backends=documentai_backends,
        response=DocumentAIResponse(urls.url_bases, urls.url_paths),
        patchers=_patchers,
    )
)
