"""Bit-level reader for AVC SPS parsing."""

from __future__ import annotations

__all__ = ("BitsReader",)


class BitsReader:
    """Read bits from a byte stream."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._byte_pos = 0
        self._bit_pos = 0

    def read_bits(self, count: int) -> int:
        """Read count bits and return as integer."""
        result = 0
        for _ in range(count):
            result = (result << 1) | self._read_bit()
        return result

    def read_bit(self) -> int:
        """Read a single bit."""
        return self._read_bit()

    def _read_bit(self) -> int:
        """Read a single bit from the stream."""
        if self._byte_pos >= len(self._data):
            raise EOFError("No more bits to read")
        byte = self._data[self._byte_pos]
        bit = (byte >> (7 - self._bit_pos)) & 1
        self._bit_pos += 1
        if self._bit_pos == 8:
            self._bit_pos = 0
            self._byte_pos += 1
        return bit

    def read_ue(self) -> int:
        """Read unsigned Exp-Golomb coded value."""
        leading_zeros = 0
        while self._read_bit() == 0:
            leading_zeros += 1
            if leading_zeros > 32:
                raise ValueError("Invalid Exp-Golomb code")
        if leading_zeros == 0:
            return 0
        return (1 << leading_zeros) - 1 + self.read_bits(leading_zeros)

    def read_se(self) -> int:
        """Read signed Exp-Golomb coded value."""
        value = self.read_ue()
        if value % 2 == 0:
            return -(value // 2)
        return (value + 1) // 2

    @property
    def bits_remaining(self) -> int:
        """Number of bits remaining."""
        return (len(self._data) - self._byte_pos) * 8 - self._bit_pos
