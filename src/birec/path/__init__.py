"""Path utilities: template variables, sidecar derivation, escape, dedup."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

__all__ = (
    "escape_path",
    "derive_path",
    "render_template",
    "deduplicate_path",
    "TEMPLATE_PATTERN",
    "SIDECAR_EXTENSIONS",
    "META_SUBDIR_NAME",
    "META_SUBDIR_EXTENSIONS",
)

# Valid template variables
TEMPLATE_PATTERN = re.compile(
    r"\{(roomid|uname|title|area|parent_area|year|month|day|hour|minute|second)\}"
)

# Sidecar file extensions
SIDECAR_EXTENSIONS = {
    ".xml",
    ".jsonl",
    ".ass",
    ".m3u8",
    ".m4s",
    ".jpg",
    ".png",
    ".meta",
    ".meta.json",
}

# Name of the subdirectory that groups the danmaku/metadata sidecars of one
# session (#37): the video and its ASS subtitle stay in the session directory
# (so players auto-load the subtitle), everything descriptive moves to meta/.
META_SUBDIR_NAME = "meta"

# Sidecar extensions tiered into META_SUBDIR_NAME under the video directory.
# .ass stays beside the video for player auto-loading, and .meta is an ffmpeg
# intermediate file the postprocessor auto-deletes beside the video.
META_SUBDIR_EXTENSIONS = frozenset({".xml", ".jsonl", ".jpg", ".png", ".meta.json"})

# Characters not allowed in file paths
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def escape_path(text: str) -> str:
    """Escape unsafe characters for use in file paths.

    Replaces characters that are invalid in file names with underscores.

    Args:
        text: Raw text to escape.

    Returns:
        Safe string for use in file paths.
    """
    return _UNSAFE_CHARS.sub("_", text).strip(". ")


def render_template(template: str, **kwargs: str | int) -> str:
    """Render a path template with variable substitution.

    Supported variables:
    {roomid}, {uname}, {title}, {area}, {parent_area},
    {year}, {month}, {day}, {hour}, {minute}, {second}

    Args:
        template: Template string with {variable} placeholders.
        **kwargs: Variable values.

    Returns:
        Rendered string with variables substituted and escaped.
    """
    # Add datetime variables if not provided
    now = datetime.now()
    defaults: dict[str, str | int] = {
        "year": now.strftime("%Y"),
        "month": now.strftime("%m"),
        "day": now.strftime("%d"),
        "hour": now.strftime("%H"),
        "minute": now.strftime("%M"),
        "second": now.strftime("%S"),
    }
    defaults.update(kwargs)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = defaults.get(key, "")
        return escape_path(str(value))

    return TEMPLATE_PATTERN.sub(_replace, template)


def derive_path(base_path: Path, extension: str) -> Path:
    """Derive a sidecar file path from a video path.

    Danmaku and metadata sidecars (extensions in ``META_SUBDIR_EXTENSIONS``)
    are tiered into the ``meta/`` subdirectory of the video's directory;
    subtitles (``.ass``) and the ffmpeg intermediate file (``.meta``) stay
    beside the video itself (#37).

    Args:
        base_path: Base file path (e.g., recording.flv).
        extension: Sidecar extension (e.g., ".xml", ".ass").

    Returns:
        Sidecar path with the new extension.
    """
    name = base_path.stem + extension
    if extension in META_SUBDIR_EXTENSIONS:
        return base_path.parent / META_SUBDIR_NAME / name
    return base_path.parent / name


def deduplicate_path(path: Path) -> Path:
    """Deduplicate a file path by appending _(n) suffix.

    If the path exists, appends _(1), _(2), etc. until a
    non-existing path is found.

    Args:
        path: Desired file path.

    Returns:
        A non-existing path (may be the original if it doesn't exist).
    """
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1

    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def validate_template(template: str) -> bool:
    """Validate that a template only contains known variables.

    Args:
        template: Template string to validate.

    Returns:
        True if all variables are valid.
    """
    # Find all {word} patterns
    all_vars = re.findall(r"\{(\w+)\}", template)
    valid_vars = {
        "roomid",
        "uname",
        "title",
        "area",
        "parent_area",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
    }
    return all(v in valid_vars for v in all_vars)
