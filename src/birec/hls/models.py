"""HLS data models."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ("HlsSegment", "HlsPlaylist", "InitSegment")


@dataclass(frozen=True, slots=True)
class HlsSegment:
    """A single HLS media segment."""

    uri: str
    duration: float
    sequence_number: int
    title: str = ""

    @property
    def filename(self) -> str:
        """Extract filename from URI."""
        return self.uri.rsplit("/", 1)[-1] if "/" in self.uri else self.uri


@dataclass(frozen=True, slots=True)
class InitSegment:
    """Initialization segment (EXT-X-MAP)."""

    uri: str

    @property
    def filename(self) -> str:
        """Extract filename from URI."""
        return self.uri.rsplit("/", 1)[-1] if "/" in self.uri else self.uri


@dataclass(frozen=True, slots=True)
class HlsPlaylist:
    """Parsed HLS playlist (m3u8)."""

    version: int = 0
    target_duration: float = 0.0
    media_sequence: int = 0
    segments: tuple[HlsSegment, ...] = field(default_factory=tuple)
    init_segment: InitSegment | None = None
    is_endlist: bool = False
    raw_text: str = ""

    @property
    def segment_count(self) -> int:
        """Number of segments in this playlist."""
        return len(self.segments)

    @property
    def total_duration(self) -> float:
        """Total duration of all segments."""
        return sum(s.duration for s in self.segments)
