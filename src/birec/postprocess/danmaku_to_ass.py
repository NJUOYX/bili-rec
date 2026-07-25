"""Danmaku XML to ASS subtitle conversion via dmconvert."""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

__all__ = ("DanmakuToAssConfig", "convert_danmaku_to_ass", "find_dmconvert")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DanmakuToAssConfig:
    """Configuration for danmaku to ASS conversion."""

    font_size: int = 25
    sc_font_size: int = 36
    resolution_x: int = 1920
    resolution_y: int = 1080


def find_dmconvert() -> str | None:
    """Find dmconvert executable path.

    Returns:
        Path to dmconvert or None if not found.
    """
    return shutil.which("dmconvert")


async def convert_danmaku_to_ass(
    xml_path: Path,
    output_path: Path,
    *,
    config: DanmakuToAssConfig | None = None,
    timeout: float = 120.0,
) -> bool:
    """Convert danmaku XML to ASS subtitle using dmconvert.

    Args:
        xml_path: Source danmaku XML file.
        output_path: Output ASS file path.
        config: Conversion configuration.
        timeout: Maximum processing time.

    Returns:
        True if successful.
    """
    dmconvert = find_dmconvert()
    if dmconvert is None:
        logger.warning("dmconvert not found, skipping ASS conversion")
        return False

    if not xml_path.exists():
        logger.error("Danmaku XML not found: %s", xml_path)
        return False

    if config is None:
        config = DanmakuToAssConfig()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        dmconvert,
        "-f",
        "xml",
        "--font-size",
        str(config.font_size),
        "--sc-font-size",
        str(config.sc_font_size),
        "--resolution",
        f"{config.resolution_x}x{config.resolution_y}",
        "-o",
        str(output_path),
        str(xml_path),
    ]

    logger.debug("Converting danmaku to ASS: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            logger.error(
                "dmconvert failed (code %d): %s",
                proc.returncode,
                stderr.decode(errors="replace")[-500:],
            )
            return False

        logger.debug("Converted %s -> %s", xml_path, output_path)
        return True

    except TimeoutError:
        logger.error("dmconvert timed out after %.0fs", timeout)
        return False
    except OSError as e:
        logger.error("Failed to run dmconvert: %s", e)
        return False
