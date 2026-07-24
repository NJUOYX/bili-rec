"""Shared pytest fixtures and configuration for the birec test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

_MARKER_BY_DIR = {"unit": "unit", "component": "component", "system": "system"}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-apply unit/component/system markers based on the test's directory."""
    tests_root = Path(__file__).parent
    for item in items:
        try:
            rel_parts = Path(item.fspath).relative_to(tests_root).parts
        except ValueError:
            continue
        if rel_parts and (marker := _MARKER_BY_DIR.get(rel_parts[0])):
            item.add_marker(getattr(pytest.mark, marker))
