"""System test: OpenAPI contract snapshot.

The committed snapshot at docs/design/openapi.json is the API contract shared
with the frontend. If this test fails, the API surface changed; regenerate the
snapshot deliberately and review the diff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "docs" / "design" / "openapi.json"

_REGENERATE_HINT = (
    "OpenAPI schema drifted from the committed contract. If the change is "
    "intentional, regenerate docs/design/openapi.json and review the diff."
)


class TestOpenApiContract:
    def test_snapshot_file_exists(self) -> None:
        assert SNAPSHOT_PATH.is_file(), _REGENERATE_HINT

    def test_schema_matches_snapshot(self, app: FastAPI) -> None:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert app.openapi() == snapshot, _REGENERATE_HINT
