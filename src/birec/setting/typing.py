"""Setting-specific type aliases."""

from __future__ import annotations

from typing import Literal

__all__ = ("RecordingMode", "CoverSaveStrategy")

RecordingMode = Literal["standard", "raw"]

CoverSaveStrategy = Literal["default", "dedup"]
