"""Remux operations: FLV→MP4 and fMP4(.m4s)→MP4 via ffmpeg."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

__all__ = ("remux_flv_to_mp4", "remux_fmp4_to_mp4", "find_ffmpeg")

logger = logging.getLogger(__name__)

# Pattern to parse ffmpeg progress output: "size= 12345kB"
_SIZE_PATTERN = re.compile(r"size=\s*(\d+)kB")


def find_ffmpeg() -> str | None:
    """Find ffmpeg executable path.

    Returns:
        Path to ffmpeg or None if not found.
    """
    return shutil.which("ffmpeg")


async def remux_flv_to_mp4(
    source: Path,
    output: Path,
    *,
    remove_filler: bool = True,
    timeout: float = 600.0,
) -> bool:
    """Remux FLV to MP4 using ffmpeg.

    Args:
        source: Source FLV file path.
        output: Output MP4 file path.
        remove_filler: Remove filler NAL units (type 12).
        timeout: Maximum processing time in seconds.

    Returns:
        True if successful, False otherwise.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        logger.error("ffmpeg not found")
        return False

    if not source.exists():
        logger.error("Source file not found: %s", source)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-codec",
        "copy",
    ]

    if remove_filler:
        cmd.extend(["-bsf:v", "filter_units=remove_types=12"])

    cmd.append(str(output))

    logger.debug("Running remux: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            logger.error(
                "ffmpeg remux failed (code %d): %s",
                proc.returncode,
                stderr.decode(errors="replace")[-500:],
            )
            return False

        logger.debug("Remuxed %s -> %s", source, output)
        return True

    except TimeoutError:
        logger.error("ffmpeg remux timed out after %.0fs", timeout)
        return False
    except OSError as e:
        logger.error("Failed to run ffmpeg: %s", e)
        return False


async def remux_fmp4_to_mp4(
    m4s_path: Path,
    output: Path,
    *,
    m3u8_path: Path | None = None,
    timeout: float = 600.0,
) -> bool:
    """Remux fMP4 (.m4s) to MP4 via a generated m3u8 playlist.

    If m3u8_path is not provided, a temporary m3u8 is generated
    referencing the m4s file.

    Args:
        m4s_path: Source .m4s file path.
        output: Output MP4 file path.
        m3u8_path: Optional existing m3u8 playlist path.
        timeout: Maximum processing time in seconds.

    Returns:
        True if successful, False otherwise.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        logger.error("ffmpeg not found")
        return False

    if not m4s_path.exists():
        logger.error("Source m4s file not found: %s", m4s_path)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)

    # Generate temporary m3u8 if not provided
    temp_m3u8: Path | None = None
    if m3u8_path is None or not m3u8_path.exists():
        temp_m3u8 = output.with_suffix(".tmp.m3u8")
        _generate_m3u8(m4s_path, temp_m3u8)
        input_path = temp_m3u8
    else:
        input_path = m3u8_path

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-codec",
        "copy",
        str(output),
    ]

    logger.debug("Running fMP4 remux: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            logger.error(
                "ffmpeg fMP4 remux failed (code %d): %s",
                proc.returncode,
                stderr.decode(errors="replace")[-500:],
            )
            return False

        logger.debug("Remuxed fMP4 %s -> %s", m4s_path, output)
        return True

    except TimeoutError:
        logger.error("ffmpeg fMP4 remux timed out after %.0fs", timeout)
        return False
    except OSError as e:
        logger.error("Failed to run ffmpeg: %s", e)
        return False
    finally:
        if temp_m3u8 is not None and temp_m3u8.exists():
            temp_m3u8.unlink()


def _generate_m3u8(m4s_path: Path, m3u8_path: Path) -> None:
    """Generate a minimal m3u8 playlist referencing the m4s file."""
    m3u8_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:7\n"
        "#EXT-X-TARGETDURATION:9999\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:9999.0,\n"
        f"{m4s_path.name}\n"
        "#EXT-X-ENDLIST\n"
    )
    m3u8_path.write_text(content, encoding="utf-8")


def parse_ffmpeg_size(stderr_line: str) -> int | None:
    """Parse size from ffmpeg stderr output.

    Args:
        stderr_line: A line from ffmpeg stderr.

    Returns:
        Size in bytes, or None if not found.
    """
    match = _SIZE_PATTERN.search(stderr_line)
    if match:
        return int(match.group(1)) * 1024
    return None
