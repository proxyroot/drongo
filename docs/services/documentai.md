# Document AI

- **Client:** `google-cloud-documentai` (`documentai_v1.DocumentProcessorServiceClient`)
- **Transport:** gRPC (the client default), forced to REST during a mock scope.
  Document AI has no emulator env var, so drongo forces the client onto its REST
  transport and serves it from the HTTP layer.
- **Backend:** per-project.

Use the normal client with no `transport` argument. Document AI uses regional
endpoints, so pass the region the same way you would against the real API.

Covers processors (create / get / list / delete, enable / disable), processor
types, batch processing, and - the headline - **document processing driven by a
handler that runs your code**, so a test exercises real extraction logic rather
than a stub.

## Create a processor and process a document

Register a **processor handler** and `process_document` runs it (like the Cloud
Run / Vertex executable handlers). The handler receives `(content, mime_type)`
and returns the resulting Document:

```python
from drongo import documentai, mock_gcp
from google.api_core.client_options import ClientOptions


@mock_gcp
def test_process():
    from google.cloud import documentai_v1

    location = "us"
    parent = f"projects/my-project/locations/{location}"
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai_v1.DocumentProcessorServiceClient(client_options=opts)

    processor = client.create_processor(
        parent=parent,
        processor=documentai_v1.Processor(type_="OCR_PROCESSOR", display_name="my-ocr"),
    )

    @documentai.processor_handler(processor.name)
    def extract(content, mime_type):
        return {
            "text": content.decode(),
            "entities": [{"type": "invoice_id", "mentionText": "INV-42"}],
        }

    response = client.process_document(
        request=documentai_v1.ProcessRequest(
            name=processor.name,
            raw_document=documentai_v1.RawDocument(
                content=b"INV-42 total $10", mime_type="text/plain"
            ),
        )
    )
    assert response.document.text == "INV-42 total $10"
    assert response.document.entities[0].type_ == "invoice_id"
```

With no handler registered, `process_document` returns the decoded input as the
document text for text mime types (empty otherwise). Missing processors raise
`google.api_core.exceptions.NotFound`.

## Coverage

| Operation | Status |
| --- | --- |
| Processors: create / get / list / delete (LRO) | Supported |
| Enable / disable processor (LRO) | Supported |
| Process document (`process_document`, via a handler) | Supported |
| Batch process (`batch_process_documents`, LRO) | Supported |
| Processor types: fetch / list / get | Supported |
| Processor versions (deploy / train / evaluate) | Planned |
| Human review, evaluations | Planned |
