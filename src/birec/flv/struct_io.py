"""Binary struct reader/writer for FLV parsing."""

from __future__ import annotations

import struct
from typing import Protocol, runtime_checkable

__all__ = ("StructReader", "StructWriter", "RandomIO")


@runtime_checkable
class RandomIO(Protocol):
    """Protocol for random-access I/O streams."""

    def read(self, size: int = -1, /) -> bytes: ...
    def write(self, data: bytes, /) -> int: ...
    def seek(self, offset: int, whence: int = 0, /) -> int: ...
    def tell(self) -> int: ...
    def close(self) -> None: ...


class StructReader:
    """Read binary data in big-endian format."""

    def __init__(self, stream: RandomIO) -> None:
        self._stream = stream

    def read(self, size: int) -> bytes:
        """Read exactly size bytes, raise EOFError if not enough."""
        data = self._stream.read(size)
        if len(data) != size:
            raise EOFError
        return data

    def read_ui8(self) -> int:
        """Read unsigned 8-bit integer."""
        return int(struct.unpack("B", self.read(1))[0])

    def read_ui16(self) -> int:
        """Read unsigned 16-bit integer (big-endian)."""
        return int(struct.unpack(">H", self.read(2))[0])

    def read_ui24(self) -> int:
        """Read unsigned 24-bit integer (big-endian)."""
        return int(struct.unpack(">I", b"\x00" + self.read(3))[0])

    def read_ui32(self) -> int:
        """Read unsigned 32-bit integer (big-endian)."""
        return int(struct.unpack(">I", self.read(4))[0])

    def read_si16(self) -> int:
        """Read signed 16-bit integer (big-endian)."""
        return int(struct.unpack(">h", self.read(2))[0])

    def read_f64(self) -> float:
        """Read 64-bit float (big-endian)."""
        return float(struct.unpack(">d", self.read(8))[0])


class StructWriter:
    """Write binary data in big-endian format."""

    def __init__(self, stream: RandomIO) -> None:
        self._stream = stream

    def write(self, data: bytes) -> int:
        """Write bytes to stream."""
        return self._stream.write(data)

    def write_ui8(self, number: int) -> int:
        """Write unsigned 8-bit integer."""
        return self.write(struct.pack("B", number))

    def write_ui16(self, number: int) -> int:
        """Write unsigned 16-bit integer (big-endian)."""
        return self.write(struct.pack(">H", number))

    def write_ui24(self, number: int) -> int:
        """Write unsigned 24-bit integer (big-endian)."""
        return self.write(struct.pack(">I", number)[1:])

    def write_ui32(self, number: int) -> int:
        """Write unsigned 32-bit integer (big-endian)."""
        return self.write(struct.pack(">I", number))

    def write_si16(self, number: int) -> int:
        """Write signed 16-bit integer (big-endian)."""
        return self.write(struct.pack(">h", number))

    def write_f64(self, number: float) -> int:
        """Write 64-bit float (big-endian)."""
        return self.write(struct.pack(">d", number))
