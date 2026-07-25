"""FFmpeg metadata injection for recorded files."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .remux import find_ffmpeg

__all__ = ("MediaMetadata", "inject_metadata")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """Metadata to inject into media files."""

    title: str = ""
    artist: str = ""
    date: str = ""
    description: str = ""
    comment: str = ""

    def to_description_json(self) -> str:
        """Serialize metadata as JSON for the description field."""
        return json.dumps(
            {
                "title": self.title,
                "artist": self.artist,
                "date": self.date,
                "description": self.description,
                "comment": self.comment,
            },
            ensure_ascii=False,
        )


async def inject_metadata(
    source: Path,
    metadata: MediaMetadata,
    *,
    output: Path | None = None,
    timeout: float = 300.0,
) -> bool:
    """Inject metadata into a media file using ffmpeg.

    If output is None, the source file is modified in-place
    (via a temporary file).

    Args:
        source: Source media file.
        metadata: Metadata to inject.
        output: Output path (None = in-place).
        timeout: Maximum processing time.

    Returns:
        True if successful.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        logger.error("ffmpeg not found")
        return False

    if not source.exists():
        logger.error("Source file not found: %s", source)
        return False

    # Use temp file for in-place modification
    if output is None:
        output = source.with_suffix(".tmp" + source.suffix)

    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-codec",
        "copy",
    ]

    if metadata.title:
        cmd.extend(["-metadata", f"title={metadata.title}"])
    if metadata.artist:
        cmd.extend(["-metadata", f"artist={metadata.artist}"])
    if metadata.date:
        cmd.extend(["-metadata", f"date={metadata.date}"])
    if metadata.description:
        cmd.extend(["-metadata", f"description={metadata.description}"])
    if metadata.comment:
        cmd.extend(["-metadata", f"comment={metadata.comment}"])

    cmd.append(str(output))

    logger.debug("Injecting metadata: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            logger.error(
                "ffmpeg metadata injection failed (code %d): %s",
                proc.returncode,
                stderr.decode(errors="replace")[-500:],
            )
            return False

        # Replace source if in-place
        if output != source and output.exists():
            source.unlink()
            output.rename(source)

        logger.debug("Injected metadata into %s", source)
        return True

    except TimeoutError:
        logger.error("ffmpeg metadata injection timed out")
        return False
    except OSError as e:
        logger.error("Failed to run ffmpeg: %s", e)
        return False
