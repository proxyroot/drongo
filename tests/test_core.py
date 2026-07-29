"""Tests for the core engine: decorator forms, reentrancy, isolation."""

from __future__ import annotations

import unittest

import pytest

from gato import get_backend, mock_gcp


def _make_bucket(name: str) -> None:
    from google.cloud import storage

    storage.Client(project="p").create_bucket(name)


def _buckets() -> dict:
    # Storage is a global namespace, so any project key returns the shared store.
    return get_backend("storage")["any-project"].buckets


def test_bare_decorator() -> None:
    @mock_gcp
    def inner() -> None:
        _make_bucket("bare")
        assert "bare" in _buckets()

    inner()
    assert _buckets() == {}  # state reset when the scope closed


def test_called_decorator() -> None:
    @mock_gcp()
    def inner() -> None:
        _make_bucket("called")
        assert "called" in _buckets()

    inner()
    assert _buckets() == {}


def test_context_manager() -> None:
    with mock_gcp():
        _make_bucket("cm")
        assert "cm" in _buckets()
    assert _buckets() == {}


def test_scopes_are_isolated() -> None:
    with mock_gcp():
        _make_bucket("first")
    with mock_gcp():
        assert _buckets() == {}


def test_reentrant_scopes_share_state() -> None:
    with mock_gcp():
        _make_bucket("outer")
        with mock_gcp():
            # A nested scope shares state and must not reset it.
            assert "outer" in _buckets()
            _make_bucket("inner")
        # Closing the inner scope must not wipe the outer scope's state.
        assert set(_buckets()) == {"outer", "inner"}
    assert _buckets() == {}


def test_fixture(gato) -> None:
    _make_bucket("fx")
    assert "fx" in gato.backend("storage").buckets


def test_get_backend_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_backend("nope")


def test_imperative_start_stop() -> None:
    mocker = mock_gcp()
    mocker.start()
    try:
        _make_bucket("imperative")
        assert "imperative" in _buckets()
    finally:
        mocker.stop()
    assert _buckets() == {}


@mock_gcp
class TestPlainClassDecorator:
    """A plain (non-unittest) test class decorated with ``mock_gcp``."""

    def test_one(self) -> None:
        _make_bucket("c1")
        assert "c1" in _buckets()

    def test_two_is_isolated(self) -> None:
        assert _buckets() == {}
        _make_bucket("c2")
        assert "c2" in _buckets()


@mock_gcp
class UnitTestStyle(unittest.TestCase):
    """A ``unittest.TestCase`` decorated with ``mock_gcp``."""

    def test_setup_teardown_wrapped(self) -> None:
        _make_bucket("u1")
        self.assertIn("u1", _buckets())
