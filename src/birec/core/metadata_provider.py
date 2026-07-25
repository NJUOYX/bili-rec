"""MetadataProvider: constructs video metadata for postprocessing."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from ..bili.models import RoomInfo, UserInfo

__all__ = ("MetadataProvider",)

UTC8 = timezone(timedelta(hours=8))


class MetadataProvider:
    """Builds video metadata dict for ffmpeg metadata injection."""

    def __init__(
        self,
        room_info: RoomInfo | None = None,
        user_info: UserInfo | None = None,
        room_id: int = 0,
    ) -> None:
        self._room_info = room_info
        self._user_info = user_info
        self._room_id = room_id
        self._live_start_time: int = 0
        self._stream_host: str = ""
        self._stream_format: str = ""
        self._stream_quality: str = ""
        self._rec_start_time: datetime | None = None

    def update(
        self,
        room_info: RoomInfo | None = None,
        user_info: UserInfo | None = None,
    ) -> None:
        if room_info is not None:
            self._room_info = room_info
            self._room_id = room_info.room_id
            self._live_start_time = room_info.live_start_time
        if user_info is not None:
            self._user_info = user_info

    def set_stream_info(
        self,
        host: str = "",
        stream_format: str = "",
        quality: str = "",
    ) -> None:
        self._stream_host = host
        self._stream_format = stream_format
        self._stream_quality = quality

    def mark_rec_start(self) -> None:
        self._rec_start_time = datetime.now(UTC8)

    def build_metadata(self) -> dict[str, Any]:
        """Build metadata dict for ffmpeg injection."""
        now = datetime.now(UTC8)
        live_start = ""
        if self._live_start_time:
            live_start = datetime.fromtimestamp(
                self._live_start_time, tz=UTC8
            ).isoformat()

        rec_start = ""
        if self._rec_start_time:
            rec_start = self._rec_start_time.isoformat()

        title = self._room_info.title if self._room_info else ""
        uname = self._user_info.name if self._user_info else ""
        area = self._room_info.area_name if self._room_info else ""
        parent_area = self._room_info.parent_area_name if self._room_info else ""

        description = json.dumps(
            {
                "room_id": self._room_id,
                "title": title,
                "area": area,
                "parent_area": parent_area,
                "live_start_time": live_start,
                "stream_host": self._stream_host,
                "stream_format": self._stream_format,
                "stream_quality": self._stream_quality,
                "rec_start_time": rec_start,
            },
            ensure_ascii=False,
        )

        return {
            "title": title,
            "artist": uname,
            "date": now.strftime("%Y-%m-%d"),
            "description": description,
            "comment": f"Recorded by birec at {rec_start}",
        }

    def build_ffmpeg_metadata(self) -> str:
        """Build ffmpeg metadata file content (INI-like format)."""
        meta = self.build_metadata()
        lines = [";FFMETADATA1"]
        for key, value in meta.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines)
