"""M3U8 playlist parsing utilities."""

from __future__ import annotations

import contextlib
import re

from .exceptions import PlaylistParseError
from .models import HlsPlaylist, HlsSegment, InitSegment

__all__ = ("parse_playlist",)

_EXTM3U = "#EXTM3U"
_EXT_VERSION = "#EXT-X-VERSION:"
_EXT_TARGET_DURATION = "#EXT-X-TARGETDURATION:"
_EXT_MEDIA_SEQUENCE = "#EXT-X-MEDIA-SEQUENCE:"
_EXT_INF = "#EXTINF:"
_EXT_MAP = "#EXT-X-MAP:"
_EXT_ENDLIST = "#EXT-X-ENDLIST"

_URI_ATTR_RE = re.compile(r'URI="([^"]+)"')


def parse_playlist(text: str) -> HlsPlaylist:
    """Parse an m3u8 playlist text into HlsPlaylist.

    Args:
        text: Raw m3u8 content.

    Returns:
        Parsed HlsPlaylist model.

    Raises:
        PlaylistParseError: If the content is not a valid m3u8.
    """
    lines = text.strip().splitlines()
    if not lines or not lines[0].strip().startswith(_EXTM3U):
        raise PlaylistParseError("missing #EXTM3U header")

    version = 0
    target_duration = 0.0
    media_sequence = 0
    segments: list[HlsSegment] = []
    init_segment: InitSegment | None = None
    is_endlist = False

    current_duration = 0.0
    current_title = ""
    seq_counter = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith(_EXT_VERSION):
            with contextlib.suppress(ValueError):
                version = int(line[len(_EXT_VERSION) :])

        elif line.startswith(_EXT_TARGET_DURATION):
            with contextlib.suppress(ValueError):
                target_duration = float(line[len(_EXT_TARGET_DURATION) :])

        elif line.startswith(_EXT_MEDIA_SEQUENCE):
            with contextlib.suppress(ValueError):
                media_sequence = int(line[len(_EXT_MEDIA_SEQUENCE) :])
                seq_counter = media_sequence

        elif line.startswith(_EXT_INF):
            value = line[len(_EXT_INF) :]
            parts = value.split(",", 1)
            try:
                current_duration = float(parts[0])
            except ValueError:
                current_duration = 0.0
            current_title = parts[1] if len(parts) > 1 else ""

        elif line.startswith(_EXT_MAP):
            attr = line[len(_EXT_MAP) :]
            match = _URI_ATTR_RE.search(attr)
            if match:
                init_segment = InitSegment(uri=match.group(1))

        elif line.startswith(_EXT_ENDLIST):
            is_endlist = True

        elif not line.startswith("#"):
            # This is a segment URI
            segments.append(
                HlsSegment(
                    uri=line,
                    duration=current_duration,
                    sequence_number=seq_counter,
                    title=current_title,
                )
            )
            seq_counter += 1
            current_duration = 0.0
            current_title = ""

    return HlsPlaylist(
        version=version,
        target_duration=target_duration,
        media_sequence=media_sequence,
        segments=tuple(segments),
        init_segment=init_segment,
        is_endlist=is_endlist,
        raw_text=text,
    )
