"""URL routing table for Document AI (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.documentai.responses import DocumentAIResponse as R

_P = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/:]+)"
_PROC = _P + r"/processors/(?P<processor>[^/:]+)"
_VER = _PROC + r"/processorVersions/(?P<version>[^/:]+)"

# Document AI uses regional endpoints (e.g. us-documentai.googleapis.com) and the
# global one; match both.
url_bases = [r"https?://([a-z0-9-]+-)?documentai\.googleapis\.com"]

url_paths = {
    # Long-running operation polling.
    f"GET {_P}/operations/(?P<operation>[^/:]+)": R.get_operation,
    # Processor actions (custom verbs first).
    f"POST {_VER}:process": R.process_document,
    f"POST {_PROC}:process": R.process_document,
    f"POST {_PROC}:batchProcess": R.batch_process,
    f"POST {_PROC}:enable": R.enable_processor,
    f"POST {_PROC}:disable": R.disable_processor,
    # Processors.
    f"POST {_P}/processors": R.create_processor,
    f"GET {_P}/processors": R.list_processors,
    f"GET {_PROC}": R.get_processor,
    f"DELETE {_PROC}": R.delete_processor,
    # Processor types.
    f"GET {_P}:fetchProcessorTypes": R.fetch_processor_types,
    f"GET {_P}/processorTypes": R.list_processor_types,
    f"GET {_P}/processorTypes/(?P<type>[^/:]+)": R.get_processor_type,
}
