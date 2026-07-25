"""Type definitions for FLV operators."""

from __future__ import annotations

from reactivex import Observable

from ..models import FlvHeader, FlvTag

__all__ = ("FLVStreamItem", "FLVStream")

type FLVStreamItem = FlvHeader | FlvTag
type FLVStream = Observable[FLVStreamItem]
