"""PathProvider: template rendering, escape, auto-dedup, auto-mkdir."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..bili.models import RoomInfo, UserInfo
from ..path import derive_path

__all__ = ("PathProvider",)

# Illegal filename characters
_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

# Path template variable pattern
_TEMPLATE_VAR_RE = re.compile(
    r"\{(roomid|uname|title|area|parent_area|year|month|day|hour|minute|second)\}"
)

# UTC+8 timezone
UTC8 = timezone(offset=timedelta(hours=8))


def escape_path(name: str) -> str:
    """Remove illegal filename characters."""
    return _ILLEGAL_CHARS_RE.sub("", name)


class PathProvider:
    """Renders output paths from templates, handles dedup and directory creation."""

    def __init__(
        self,
        out_dir: str,
        path_template: str,
        room_info: RoomInfo | None = None,
        user_info: UserInfo | None = None,
    ) -> None:
        self._out_dir = os.path.expanduser(out_dir)
        self._path_template = path_template
        self._room_info = room_info
        self._user_info = user_info

    @property
    def out_dir(self) -> str:
        return self._out_dir

    @out_dir.setter
    def out_dir(self, value: str) -> None:
        self._out_dir = os.path.expanduser(value)

    def update_info(
        self,
        room_info: RoomInfo | None = None,
        user_info: UserInfo | None = None,
    ) -> None:
        """Update room/user info for template rendering."""
        if room_info is not None:
            self._room_info = room_info
        if user_info is not None:
            self._user_info = user_info

    def render(self, now: datetime | None = None) -> str:
        """Render the path template with current info and time."""
        if now is None:
            now = datetime.now(UTC8)

        variables: dict[str, str] = {}
        if self._room_info:
            variables["roomid"] = str(self._room_info.room_id)
            variables["title"] = escape_path(self._room_info.title)
            variables["area"] = escape_path(self._room_info.area_name)
            variables["parent_area"] = escape_path(self._room_info.parent_area_name)
        if self._user_info:
            variables["uname"] = escape_path(self._user_info.name)

        variables["year"] = str(now.year)
        variables["month"] = f"{now.month:02d}"
        variables["day"] = f"{now.day:02d}"
        variables["hour"] = f"{now.hour:02d}"
        variables["minute"] = f"{now.minute:02d}"
        variables["second"] = f"{now.second:02d}"

        # Fill missing variables with defaults
        for match in _TEMPLATE_VAR_RE.finditer(self._path_template):
            var = match.group(1)
            if var not in variables:
                variables[var] = ""

        path = self._path_template.format(**variables)
        return os.path.join(self._out_dir, path)

    def make_dirs(self, path: str) -> str:
        """Create parent directories for the given path and return it."""
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        return path

    def dedup(self, path: str, suffix: str = "") -> str:
        """Ensure unique path by appending _(n) if file exists.

        Args:
            path: Base path without extension.
            suffix: File extension (e.g. '.flv', '.xml').
        """
        full = path + suffix
        if not os.path.exists(full):
            return full

        counter = 1
        while True:
            full = f"{path}_{counter}{suffix}"
            if not os.path.exists(full):
                return full
            counter += 1

    def video_path(self, now: datetime | None = None) -> str:
        """Render and dedup a video file path."""
        base = self.render(now)
        return self.dedup(base, ".flv")

    def _meta_sidecar_path(self, video_path: str, extension: str) -> str:
        """Derive a danmaku/metadata sidecar path in the session's ``meta/``.

        Creates the ``meta/`` directory: the dumpers open their files right
        after the path is handed to them (#37).
        """
        path = derive_path(Path(video_path), extension)
        os.makedirs(path.parent, exist_ok=True)
        return str(path)

    def danmaku_path(self, video_path: str) -> str:
        """Derive danmaku XML path (tiered into the ``meta/`` subdirectory)."""
        return self._meta_sidecar_path(video_path, ".xml")

    def raw_danmaku_path(self, video_path: str) -> str:
        """Derive raw danmaku JSONL path (tiered into ``meta/``)."""
        return self._meta_sidecar_path(video_path, ".jsonl")

    def cover_path(self, video_path: str, ext: str = ".jpg") -> str:
        """Derive cover image path (tiered into ``meta/``)."""
        return self._meta_sidecar_path(video_path, ext)

    def meta_path(self, video_path: str) -> str:
        """Derive ffmpeg metadata file path from video path.

        Stays beside the video: it is an intermediate file the postprocessor
        auto-deletes once the remux succeeds (#37).
        """
        return os.path.splitext(video_path)[0] + ".meta"

    def meta_json_path(self, video_path: str) -> str:
        """Derive extra metadata JSON path (tiered into ``meta/``)."""
        return self._meta_sidecar_path(video_path, ".meta.json")
