"""Document AI tests using the real documentai_v1 client (forced REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc
from google.api_core.client_options import ClientOptions

pytest.importorskip("google.cloud.documentai_v1")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
LOCATION = "us"
PARENT = f"projects/{PROJECT}/locations/{LOCATION}"
_OPTS = ClientOptions(api_endpoint=f"{LOCATION}-documentai.googleapis.com")


def _client():
    from google.cloud import documentai_v1

    return documentai_v1.DocumentProcessorServiceClient(client_options=_OPTS)


def _processor(client):
    from google.cloud import documentai_v1

    return client.create_processor(
        parent=PARENT,
        processor=documentai_v1.Processor(type_="OCR_PROCESSOR", display_name="ocr"),
    )


# -- processors -------------------------------------------------------------


def test_processor_create_get_list_delete() -> None:
    from google.cloud import documentai_v1

    client = _client()
    processor = _processor(client)
    assert processor.name.startswith(f"{PARENT}/processors/")
    assert processor.state == documentai_v1.Processor.State.ENABLED

    assert client.get_processor(name=processor.name).display_name == "ocr"
    assert [
        p.display_name for p in client.list_processors(parent=PARENT).processors
    ] == ["ocr"]

    client.delete_processor(name=processor.name).result()  # LRO
    assert list(client.list_processors(parent=PARENT).processors) == []


def test_enable_disable_processor() -> None:
    from google.cloud import documentai_v1

    client = _client()
    processor = _processor(client)

    client.disable_processor(
        request=documentai_v1.DisableProcessorRequest(name=processor.name)
    ).result()
    assert (
        client.get_processor(name=processor.name).state
        == documentai_v1.Processor.State.DISABLED
    )

    client.enable_processor(
        request=documentai_v1.EnableProcessorRequest(name=processor.name)
    ).result()
    assert (
        client.get_processor(name=processor.name).state
        == documentai_v1.Processor.State.ENABLED
    )


def test_get_missing_processor_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_processor(name=f"{PARENT}/processors/ghost")


# -- processor types --------------------------------------------------------


def test_fetch_and_list_processor_types() -> None:
    client = _client()
    fetched = client.fetch_processor_types(parent=PARENT)
    assert "OCR_PROCESSOR" in [t.type_ for t in fetched.processor_types]
    listed = client.list_processor_types(parent=PARENT)
    assert "FORM_PARSER_PROCESSOR" in [t.type_ for t in listed.processor_types]


# -- processing -------------------------------------------------------------


def test_process_document_without_handler_returns_text() -> None:
    from google.cloud import documentai_v1

    client = _client()
    processor = _processor(client)
    response = client.process_document(
        request=documentai_v1.ProcessRequest(
            name=processor.name,
            raw_document=documentai_v1.RawDocument(
                content=b"hello world", mime_type="text/plain"
            ),
        )
    )
    assert response.document.text == "hello world"


def test_process_document_runs_registered_handler() -> None:
    from google.cloud import documentai_v1

    from drongo.services import documentai

    client = _client()
    processor = _processor(client)

    @documentai.processor_handler(processor.name)
    def extract(content, mime_type):
        return {
            "text": content.decode().upper(),
            "entities": [{"type": "greeting", "mentionText": content.decode()}],
        }

    response = client.process_document(
        request=documentai_v1.ProcessRequest(
            name=processor.name,
            raw_document=documentai_v1.RawDocument(
                content=b"hi there", mime_type="text/plain"
            ),
        )
    )
    assert response.document.text == "HI THERE"
    assert [(e.type_, e.mention_text) for e in response.document.entities] == [
        ("greeting", "hi there")
    ]


def test_batch_process_documents_completes() -> None:
    from google.cloud import documentai_v1

    client = _client()
    processor = _processor(client)
    operation = client.batch_process_documents(
        request=documentai_v1.BatchProcessRequest(name=processor.name)
    )
    operation.result()  # LRO completes synchronously
    assert operation.done()
