"""In-memory models for Document AI (``documentai`` v1).

Document AI defaults to gRPC but ships a REST transport and has no emulator env
var, so drongo forces the client onto REST (see ``__init__.py``) and serves it
from the HTTP layer. Processors are stored as the proto-JSON the client sent and
echoed back on get/list.

The headline call, ``ProcessDocument``, runs a registered **processor handler**
so a test drives real extraction logic on a mocked processor, rather than a stub
(mirroring the Cloud Run / Vertex executable handlers). With no handler, the
document text is the decoded input for text mime types, else empty.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["DocumentAIBackend", "ProcessorHandler", "documentai_backends"]

#: A processor handler receives the input ``(content, mime_type)`` and returns
#: the resulting Document as a proto-JSON dict (e.g. ``{"text": "...", ...}``).
ProcessorHandler = Callable[[bytes, str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class DocumentAIBackend(BaseBackend):
    """In-memory Document AI state for a single project."""

    def setup(self) -> None:
        self.processors: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.processor_handlers: dict[str, ProcessorHandler] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    # -- long-running operations ------------------------------------------

    def operation(self, parent: str, response: dict[str, Any] | None) -> dict[str, Any]:
        name = f"{parent}/operations/{self._next()}"
        op: dict[str, Any] = {"name": name, "done": True}
        if response is not None:
            op["response"] = response
        self.operations[name] = op
        return op

    def get_operation(self, name: str) -> dict[str, Any]:
        return self.operations.get(name, {"name": name, "done": True})

    # -- processors --------------------------------------------------------

    def create_processor(
        self, parent: str, processor: dict[str, Any]
    ) -> dict[str, Any]:
        processor = dict(processor)
        processor["name"] = f"{parent}/processors/{self._next()}"
        processor.setdefault("state", "ENABLED")
        processor.setdefault("createTime", _now())
        self.processors[processor["name"]] = processor
        return processor

    def get_processor(self, name: str) -> dict[str, Any]:
        try:
            return self.processors[name]
        except KeyError:
            raise exceptions.not_found(f"Processor not found: {name}")

    def list_processors(self, parent: str) -> list[dict[str, Any]]:
        prefix = f"{parent}/processors/"
        return [
            self.processors[n]
            for n in sorted(self.processors)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]

    def delete_processor(self, name: str) -> None:
        self.get_processor(name)
        del self.processors[name]

    def set_state(self, name: str, state: str) -> dict[str, Any]:
        processor = self.get_processor(name)
        processor["state"] = state
        return processor

    # -- processing --------------------------------------------------------

    def register_processor_handler(self, name: str, handler: ProcessorHandler) -> None:
        """Bind a callable that produces the Document for a processor's process."""
        self.processor_handlers[name] = handler

    def process(self, name: str, content: bytes, mime_type: str) -> dict[str, Any]:
        """Run the processor's handler (or return the decoded text as a Document)."""
        processor = name.split("/processorVersions/")[0]
        self.get_processor(processor)  # 404 if the processor does not exist
        handler = self.processor_handlers.get(processor)
        if handler is not None:
            return handler(content, mime_type)
        text = (
            content.decode("utf-8", "replace") if mime_type.startswith("text/") else ""
        )
        return {"text": text, "mimeType": mime_type}


#: Project-keyed backends, inspectable via ``get_backend("documentai")[project]``.
documentai_backends: BackendDict[DocumentAIBackend] = BackendDict(
    DocumentAIBackend, "documentai"
)
