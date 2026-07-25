"""Postprocessing models: status, progress, and task items."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = (
    "PostprocessingStatus",
    "PostprocessingProgress",
    "PostprocessingItem",
)


class PostprocessingStatus(Enum):
    """Status of a postprocessing task."""

    WAITING = "waiting"
    REMUXING = "remuxing"
    INJECTING = "injecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PostprocessingProgress:
    """Progress of a postprocessing operation."""

    status: PostprocessingStatus = PostprocessingStatus.WAITING
    percent: float = 0.0  # 0.0 - 100.0
    current_size: int = 0  # bytes written so far
    total_size: int = 0  # expected total bytes (0 if unknown)


@dataclass(slots=True)
class PostprocessingItem:
    """A single postprocessing task item."""

    source_path: Path
    output_path: Path
    status: PostprocessingStatus = PostprocessingStatus.WAITING
    progress: PostprocessingProgress = field(default_factory=PostprocessingProgress)
    related_files: list[Path] = field(default_factory=list)
    error: str = ""

    @property
    def is_done(self) -> bool:
        """Check if processing is complete (success or failure)."""
        return self.status in (
            PostprocessingStatus.COMPLETED,
            PostprocessingStatus.FAILED,
        )
