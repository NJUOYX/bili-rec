"""StreamParamHolder: quality fallback, platform rotation, alternative stream toggle."""

from __future__ import annotations

from ..bili.typing import ApiPlatform, QualityNumber, StreamCodec, StreamFormat

__all__ = ("StreamParamHolder",)

# Quality fallback order (highest to lowest)
_QUALITY_FALLBACK: list[QualityNumber] = [
    20000,  # 4K
    10000,  # 原画
    401,  # 蓝光(杜比)
    400,  # 蓝光
    250,  # 超清
    150,  # 高清
    80,  # 流畅
]

# Platform rotation order
_PLATFORMS: list[ApiPlatform] = ["web", "android"]


class StreamParamHolder:
    """Manages stream parameter fallback chains.

    When the target quality/format/codec is unavailable, provides the next
    best option to try.
    """

    def __init__(
        self,
        stream_format: StreamFormat = "flv",
        stream_codec: StreamCodec = "avc",
        quality_number: QualityNumber = 10000,
    ) -> None:
        self._stream_format = stream_format
        self._stream_codec = stream_codec
        self._quality_number = quality_number
        self._original_quality = quality_number
        self._platform_idx = 0
        self._use_alternative = False

    @property
    def stream_format(self) -> StreamFormat:
        return self._stream_format

    @stream_format.setter
    def stream_format(self, value: StreamFormat) -> None:
        self._stream_format = value

    @property
    def stream_codec(self) -> StreamCodec:
        return self._stream_codec

    @stream_codec.setter
    def stream_codec(self, value: StreamCodec) -> None:
        self._stream_codec = value

    @property
    def quality_number(self) -> QualityNumber:
        return self._quality_number

    @quality_number.setter
    def quality_number(self, value: QualityNumber) -> None:
        self._quality_number = value

    @property
    def use_alternative(self) -> bool:
        return self._use_alternative

    @use_alternative.setter
    def use_alternative(self, value: bool) -> None:
        self._use_alternative = value

    def fallback_quality(self) -> QualityNumber | None:
        """Return the next lower quality, or None if already at lowest."""
        try:
            idx = _QUALITY_FALLBACK.index(self._quality_number)
        except ValueError:
            return None
        if idx + 1 < len(_QUALITY_FALLBACK):
            self._quality_number = _QUALITY_FALLBACK[idx + 1]
            return self._quality_number
        return None

    def reset_quality(self) -> None:
        """Reset quality to the original target."""
        self._quality_number = self._original_quality

    def next_platform(self) -> ApiPlatform | None:
        """Return the next API platform, or None if exhausted."""
        self._platform_idx += 1
        if self._platform_idx < len(_PLATFORMS):
            return _PLATFORMS[self._platform_idx]
        return None

    def reset_platform(self) -> None:
        """Reset platform rotation to the first option."""
        self._platform_idx = 0

    def reset(self) -> None:
        """Reset all fallback state."""
        self.reset_quality()
        self.reset_platform()
        self._use_alternative = False
