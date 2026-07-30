"""Cloud Logging tests using the real client, served by drongo's gRPC emulator.

The google-cloud-logging library writes one diagnostic/instrumentation entry on
its first write per client; these tests filter it out and assert on the entries
the test itself wrote.
"""

from __future__ import annotations

import pytest

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
RESOURCES = [f"projects/{PROJECT}"]


def _client():
    import google.cloud.logging as logging

    return logging.Client(project=PROJECT)


def _payloads(entries):
    """Payloads of the entries the test wrote (drop the client's own diagnostic)."""
    out = []
    for entry in entries:
        payload = entry.payload
        if isinstance(payload, dict) and "logging.googleapis.com/diagnostic" in payload:
            continue
        out.append(payload)
    return out


def test_write_text_and_list() -> None:
    client = _client()
    client.logger("app").log_text("hello world", severity="INFO")

    entries = list(client.list_entries(resource_names=RESOURCES))
    assert _payloads(entries) == ["hello world"]
    written = next(e for e in entries if e.payload == "hello world")
    assert written.severity == "INFO"


def test_log_struct() -> None:
    client = _client()
    client.logger("app").log_struct({"event": "signup", "user": 42})

    entries = list(client.list_entries(resource_names=RESOURCES))
    assert _payloads(entries) == [{"event": "signup", "user": 42.0}]


def test_ordering_descending() -> None:
    client = _client()
    logger = client.logger("app")
    logger.log_text("first")
    logger.log_text("second")

    from google.cloud.logging import DESCENDING

    entries = list(client.list_entries(resource_names=RESOURCES, order_by=DESCENDING))
    assert _payloads(entries) == ["second", "first"]


def test_multiple_loggers_and_list_logs() -> None:
    client = _client()
    client.logger("a").log_text("x")
    client.logger("b").log_text("y")

    backend = get_backend("logging")["_"]
    logs = set(backend.list_logs(PROJECT))
    assert f"projects/{PROJECT}/logs/a" in logs
    assert f"projects/{PROJECT}/logs/b" in logs


def test_delete_log() -> None:
    client = _client()
    client.logger("app").log_text("temp")
    assert _payloads(list(client.list_entries(resource_names=RESOURCES))) == ["temp"]

    client.logger("app").delete()
    remaining = _payloads(list(client.list_entries(resource_names=RESOURCES)))
    assert remaining == []


def test_backend_is_inspectable() -> None:
    client = _client()
    client.logger("app").log_text("inspect me")
    entries = get_backend("logging")["_"].entries
    assert any(e.log_name == f"projects/{PROJECT}/logs/app" for e in entries)
