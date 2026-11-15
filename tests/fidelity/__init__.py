"""Dual-target fidelity tests: one test body, two targets.

Every scenario in this package is decorated with :func:`gcp_verified`. The body
never branches on the target:

* by default it runs under ``mock_gcp``, so it is an ordinary unit test and PR
  CI needs no credentials;
* when ``DRONGO_TEST_ALLOW_GCP_REQUEST=true`` and ``DRONGO_TEST_PROJECT`` are
  set it runs against **real GCP** using Application Default Credentials.

The point is the second mode. A scenario is written and adjusted until it passes
against real GCP, so the assertions record how GCP actually behaves rather than
how the docs read; drongo is then held to the same test. This mirrors moto's
``@aws_verified`` and the approach AWS describes for its own emulator.

Because of that, these tests assert on *behaviour* - status codes, error types,
state transitions, which fields come back - and never on volatile values such as
etags, timestamps or the exact generation number, which differ between a real
project and the mock.

Where drongo passes against GCP but diverges under the mock, the scenario is
marked ``pytest.mark.xfail(strict=True)`` via :func:`known_gap` and listed in
``KNOWN_GAPS.md``. Strict xfail means the marker has to be removed when the gap
is fixed, so the list cannot silently rot.

Running against real GCP::

    export DRONGO_TEST_ALLOW_GCP_REQUEST=true
    export DRONGO_TEST_PROJECT=my-sandbox-project
    gcloud auth application-default login
    pytest tests/fidelity -v

Live runs create real, billable resources. Every one is named with a
run-unique prefix and labelled, and both per-test teardown and an end-of-session
sweep delete anything carrying the label, so a failed run does not leak.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

#: Set to a truthy value to send this suite at real GCP instead of the mock.
ALLOW_LIVE_ENV = "DRONGO_TEST_ALLOW_GCP_REQUEST"

#: The project a live run creates its resources in. Required when live.
PROJECT_ENV = "DRONGO_TEST_PROJECT"

#: Resource-name prefix and label key stamped on everything a run creates.
#: Both the per-test teardown and the session sweep key off this.
FIDELITY_PREFIX = "drongo-fid"
FIDELITY_LABEL = "drongo-fidelity"

_TRUTHY = {"1", "true", "yes", "on"}

F = TypeVar("F", bound=Callable[..., Any])


def live_requests_allowed() -> bool:
    """Whether this run should talk to real GCP."""
    return os.environ.get(ALLOW_LIVE_ENV, "").strip().lower() in _TRUTHY


def live_project() -> str:
    """The project to use for a live run.

    Raises a usage error rather than falling back to a default: creating
    resources in whatever project the ambient credentials happen to point at is
    exactly the accident worth preventing.
    """
    project = os.environ.get(PROJECT_ENV, "").strip()
    if not project:
        raise pytest.UsageError(
            f"{ALLOW_LIVE_ENV} is set, so the fidelity suite would run against "
            f"real GCP, but {PROJECT_ENV} is empty. Set it to a sandbox project "
            f"you are happy to create and delete resources in."
        )
    return project


def gcp_verified(func: F) -> F:
    """Mark a test as a fidelity scenario verified against real GCP.

    Requests the ``gcp_target`` fixture, which either activates ``mock_gcp`` or
    points the test at ``DRONGO_TEST_PROJECT``, and tags the test with the
    ``gcp_verified`` marker so the suite can be selected with ``-m``.
    """
    func = pytest.mark.usefixtures("gcp_target")(func)
    return pytest.mark.gcp_verified(func)


def known_gap(reason: str) -> pytest.MarkDecorator:
    """Mark a scenario that passes against GCP but fails under drongo.

    ``strict=True`` means an unexpected *pass* fails the suite, so closing the
    gap forces the marker off and keeps ``KNOWN_GAPS.md`` honest. A live run
    skips the marker entirely, since the behaviour is GCP's own.
    """
    return pytest.mark.xfail(not live_requests_allowed(), reason=reason, strict=True)
