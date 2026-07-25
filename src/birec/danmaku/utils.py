"""Danmaku file utilities: merge, check, clear, copy."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .models import DanmakuDocument
from .reader import DanmakuReader
from .writer import DanmakuWriter

__all__ = ("merge_danmaku", "has_danmu", "clear_danmu", "copy_danmus")

logger = logging.getLogger(__name__)

_reader = DanmakuReader()
_writer = DanmakuWriter()


def has_danmu(path: Path | str) -> bool:
    """Check if a danmaku XML file contains any danmaku items.

    Args:
        path: Path to the danmaku XML file.

    Returns:
        True if the file exists and contains at least one item.
    """
    path = Path(path)
    if not path.exists():
        return False
    try:
        doc = _reader.read(path)
        return not doc.is_empty()
    except (ValueError, OSError):
        return False


def clear_danmu(path: Path | str) -> None:
    """Clear all danmaku items from a file, keeping metadata.

    Args:
        path: Path to the danmaku XML file.
    """
    path = Path(path)
    if not path.exists():
        return

    try:
        doc = _reader.read(path)
    except (ValueError, OSError):
        return

    # Keep metadata, clear all items
    cleared = DanmakuDocument(metadata=doc.metadata)
    _writer.write(cleared, path)
    logger.debug("Cleared danmaku items from %s", path)


def copy_danmus(src: Path | str, dst: Path | str) -> None:
    """Copy a danmaku file from src to dst.

    Args:
        src: Source danmaku XML file.
        dst: Destination path.
    """
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    logger.debug("Copied danmaku %s -> %s", src, dst)


def merge_danmaku(
    src: Path | str,
    dst: Path | str,
    *,
    prepend: bool = False,
) -> int:
    """Merge src danmaku file into dst.

    After merging, src is cleared (items removed) and dst is
    atomically replaced with the merged result.

    Args:
        src: Source danmaku XML file (will be cleared after merge).
        dst: Destination danmaku XML file.
        prepend: If True, src items are inserted before dst items.
            If False, src items are appended after dst items.

    Returns:
        Number of items merged from src.
    """
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        return 0

    try:
        src_doc = _reader.read(src)
    except (ValueError, OSError) as e:
        logger.warning("Failed to read src danmaku %s: %s", src, e)
        return 0

    if src_doc.is_empty():
        return 0

    # Read dst if it exists
    dst_doc = DanmakuDocument()
    if dst.exists():
        try:
            dst_doc = _reader.read(dst)
        except (ValueError, OSError):
            dst_doc = DanmakuDocument()

    # Merge
    merged_count = src_doc.total_count
    merged = _merge_docs(src_doc, dst_doc) if prepend else _merge_docs(dst_doc, src_doc)

    # Write merged result to dst
    _writer.write(merged, dst)

    # Clear src
    cleared = DanmakuDocument(metadata=src_doc.metadata)
    _writer.write(cleared, src)

    logger.debug(
        "Merged %d items from %s into %s (prepend=%s)",
        merged_count,
        src,
        dst,
        prepend,
    )
    return merged_count


def _merge_docs(first: DanmakuDocument, second: DanmakuDocument) -> DanmakuDocument:
    """Merge two documents: first items come before second items."""
    result = DanmakuDocument()
    result.metadata = first.metadata or second.metadata
    result.danmakus = first.danmakus + second.danmakus
    result.super_chats = first.super_chats + second.super_chats
    result.gifts = first.gifts + second.gifts
    result.guards = first.guards + second.guards
    result.toasts = first.toasts + second.toasts
    return result
