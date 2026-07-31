"""Growing byte buffer for parsing a live FLV stream chunk by chunk."""

from __future__ import annotations

from io import SEEK_CUR, SEEK_END, SEEK_SET

__all__ = ("StreamBuffer",)


class StreamBuffer:
    """Append-only stream with random access over the unconsumed window.

    A live FLV download arrives as arbitrary HTTP chunks that cut tags in half,
    so the parser has to rewind to the start of the unfinished tag and resume
    once the remaining bytes land. This buffer keeps every byte from the current
    read position onward and reports absolute stream offsets, so tag offsets stay
    stable across chunk boundaries; :meth:`discard_consumed` drops the
    already-parsed prefix to keep memory bounded.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        # Absolute stream offset of self._buf[0].
        self._origin = 0
        # Absolute read position.
        self._pos = 0

    def append(self, data: bytes) -> None:
        """Append newly received bytes to the end of the stream."""
        self._buf += data

    def discard_consumed(self) -> None:
        """Drop the bytes before the current read position."""
        consumed = self._pos - self._origin
        if consumed <= 0:
            return
        del self._buf[:consumed]
        self._origin = self._pos

    def discard_unparsed(self) -> None:
        """Drop the bytes after the current read position.

        For when the stream restarts. A connection can die anywhere, including
        halfway through a tag, and what it left behind belongs to a document
        that has ended. The bytes arriving next are the start of a new one, so
        splicing them onto the fragment would leave the parser reading a tag
        length out of two unrelated streams and misaligned from there on.
        """
        keep = self._pos - self._origin
        if keep < 0 or keep >= len(self._buf):
            return
        del self._buf[keep:]

    @property
    def buffered(self) -> int:
        """Number of bytes currently retained in memory."""
        return len(self._buf)

    # ── RandomIO protocol ────────────────────────────────────────────────

    def read(self, size: int = -1, /) -> bytes:
        """Read up to ``size`` bytes; a short read signals "not yet arrived"."""
        start = self._pos - self._origin
        if start < 0:
            raise ValueError(f"Read position {self._pos} was already discarded")
        if size < 0:
            data = bytes(self._buf[start:])
        else:
            data = bytes(self._buf[start : start + size])
        self._pos += len(data)
        return data

    def write(self, data: bytes, /) -> int:
        raise OSError("StreamBuffer is read-only, use append()")

    def seek(self, offset: int, whence: int = SEEK_SET, /) -> int:
        if whence == SEEK_SET:
            pos = offset
        elif whence == SEEK_CUR:
            pos = self._pos + offset
        elif whence == SEEK_END:
            pos = self._origin + len(self._buf) + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if pos < self._origin:
            raise ValueError(
                f"Cannot seek to {pos}: bytes before {self._origin} were discarded"
            )
        self._pos = pos
        return pos

    def tell(self) -> int:
        return self._pos

    def close(self) -> None:
        self._buf.clear()
        self._origin = self._pos
