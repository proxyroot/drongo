"""Keep ``KNOWN_GAPS.md`` and the ``@known_gap`` markers in agreement.

The strict xfail already stops a *fixed* gap from being quietly listed: the
scenario starts failing. It cannot catch the other two drifts, which this test
does:

* a gap marked in the suite but never written up, so users never hear about it;
* a row left in the document after its scenario was renamed or deleted.

The markers are read from the source with ``ast`` rather than by introspecting
collected items, so this stays a plain assertion about the two files and does
not depend on which target the suite is pointed at.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

FIDELITY_DIR = Path(__file__).parent
KNOWN_GAPS = FIDELITY_DIR.parent.parent / "KNOWN_GAPS.md"

#: Lines in KNOWN_GAPS.md that name the scenario proving a gap.
_SCENARIO_LINE = re.compile(r"^- Scenario: `(?P<node_id>[^`]+)`$", re.MULTILINE)


def _marked_scenarios() -> set[str]:
    """Node ids of every ``@known_gap``-decorated test in this package."""
    found: set[str] = set()
    for path in sorted(FIDELITY_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if any(_is_known_gap(decorator) for decorator in node.decorator_list):
                found.add(f"tests/fidelity/{path.name}::{node.name}")
    return found


def _is_known_gap(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "known_gap"
    )


def _documented_scenarios() -> set[str]:
    return {
        match.group("node_id")
        for match in _SCENARIO_LINE.finditer(KNOWN_GAPS.read_text())
    }


def test_every_known_gap_is_documented() -> None:
    undocumented = _marked_scenarios() - _documented_scenarios()

    assert not undocumented, (
        "these scenarios are marked @known_gap but are missing from "
        f"KNOWN_GAPS.md: {sorted(undocumented)}"
    )


def test_every_documented_gap_still_exists() -> None:
    stale = _documented_scenarios() - _marked_scenarios()

    assert not stale, (
        "KNOWN_GAPS.md lists scenarios that are no longer marked @known_gap "
        f"(renamed, deleted, or fixed): {sorted(stale)}"
    )


def test_known_gaps_document_lists_something() -> None:
    """Guard against a regex that silently matches nothing."""
    assert _documented_scenarios()
