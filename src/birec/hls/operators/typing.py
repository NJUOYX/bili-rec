"""Type definitions for HLS operators."""

from __future__ import annotations

from reactivex import Observable

from ..models import HlsPlaylist, HlsSegment

__all__ = ("HLSStreamItem", "HLSStream")

type HLSStreamItem = HlsPlaylist | HlsSegment
type HLSStream = Observable[HLSStreamItem]
