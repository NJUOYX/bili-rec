"""Danmaku XML to ASS subtitle conversion via dmconvert."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

__all__ = ("DanmakuToAssConfig", "convert_danmaku_to_ass")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DanmakuToAssConfig:
    """Configuration for danmaku to ASS conversion."""

    font_size: int = 25
    sc_font_size: int = 36
    resolution_x: int = 1920
    resolution_y: int = 1080


async def convert_danmaku_to_ass(
    xml_path: Path,
    output_path: Path,
    *,
    config: DanmakuToAssConfig | None = None,
    timeout: float = 120.0,
) -> bool:
    """Convert danmaku XML to ASS subtitle using dmconvert.

    dmconvert is a pure-Python library and a declared dependency, so it is
    called in-process rather than through its console script: that removes the
    need for it to be on ``PATH`` and keeps the argument list from drifting away
    from the one its CLI accepts.

    Args:
        xml_path: Source danmaku XML file.
        output_path: Output ASS file path.
        config: Conversion configuration.
        timeout: Maximum time to wait for the conversion.

    Returns:
        True if successful.
    """
    try:
        from dmconvert import convert_xml_to_ass
    except ImportError:
        logger.warning("dmconvert is not installed, skipping ASS conversion")
        return False

    if not xml_path.exists():
        logger.error("Danmaku XML not found: %s", xml_path)
        return False

    if config is None:
        config = DanmakuToAssConfig()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Converting danmaku to ASS: %s -> %s", xml_path, output_path)

    try:
        # The conversion parses the whole XML and is CPU-bound, so it goes to a
        # worker thread to keep the event loop responsive. A timeout only stops
        # us waiting; the thread itself cannot be interrupted.
        await asyncio.wait_for(
            asyncio.to_thread(
                convert_xml_to_ass,
                config.font_size,
                config.sc_font_size,
                config.resolution_x,
                config.resolution_y,
                str(xml_path),
                str(output_path),
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.error("Danmaku conversion timed out after %.0fs", timeout)
        return False
    except Exception:
        logger.exception("Failed to convert danmaku to ASS: %s", xml_path)
        return False

    logger.debug("Converted %s -> %s", xml_path, output_path)
    return True
