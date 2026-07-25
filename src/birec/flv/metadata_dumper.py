"""Metadata JSON dumper for FLV files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ("dump_metadata", "load_metadata")


def dump_metadata(metadata: dict[str, Any], path: Path) -> None:
    """Dump metadata to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def load_metadata(path: Path) -> dict[str, Any]:
    """Load metadata from a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]
