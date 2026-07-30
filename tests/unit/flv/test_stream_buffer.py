"""Tests for StreamBuffer, the resumable buffer behind live FLV parsing."""

from __future__ import annotations

from io import SEEK_CUR, SEEK_END

import pytest

from birec.flv.stream_buffer import StreamBuffer


class TestStreamBufferReads:
    def test_reads_appended_data(self) -> None:
        buf = StreamBuffer()
        buf.append(b"abcdef")
        assert buf.read(3) == b"abc"
        assert buf.tell() == 3
        assert buf.read() == b"def"

    def test_short_read_signals_missing_data(self) -> None:
        """A short read is how the parser learns to wait for the next chunk."""
        buf = StreamBuffer()
        buf.append(b"ab")
        assert buf.read(5) == b"ab"
        assert buf.tell() == 2

    def test_read_resumes_after_append(self) -> None:
        buf = StreamBuffer()
        buf.append(b"ab")
        assert buf.read(4) == b"ab"
        buf.seek(0)
        buf.append(b"cd")
        assert buf.read(4) == b"abcd"

    def test_write_is_rejected(self) -> None:
        buf = StreamBuffer()
        with pytest.raises(OSError, match="read-only"):
            buf.write(b"x")


class TestStreamBufferSeek:
    def test_seek_set_cur_end(self) -> None:
        buf = StreamBuffer()
        buf.append(b"0123456789")
        assert buf.seek(4) == 4
        assert buf.seek(2, SEEK_CUR) == 6
        assert buf.seek(-1, SEEK_END) == 9
        assert buf.read() == b"9"

    def test_rewind_lets_a_split_tag_be_reparsed(self) -> None:
        buf = StreamBuffer()
        buf.append(b"header-")
        start = buf.tell()
        assert buf.read(20) == b"header-"
        buf.seek(start)
        buf.append(b"body")
        assert buf.read(11) == b"header-body"

    def test_unsupported_whence_rejected(self) -> None:
        buf = StreamBuffer()
        with pytest.raises(ValueError, match="whence"):
            buf.seek(0, 99)


class TestStreamBufferDiscard:
    def test_discard_releases_memory_but_keeps_offsets(self) -> None:
        """Offsets stay absolute so FLV tag offsets remain meaningful."""
        buf = StreamBuffer()
        buf.append(b"0123456789")
        buf.read(6)
        buf.discard_consumed()

        assert buf.buffered == 4
        assert buf.tell() == 6
        assert buf.read() == b"6789"

    def test_discard_is_a_noop_at_the_start(self) -> None:
        buf = StreamBuffer()
        buf.append(b"abc")
        buf.discard_consumed()
        assert buf.buffered == 3
        assert buf.read() == b"abc"

    def test_seeking_into_discarded_range_is_refused(self) -> None:
        """Silently returning wrong bytes would corrupt the recording."""
        buf = StreamBuffer()
        buf.append(b"0123456789")
        buf.read(6)
        buf.discard_consumed()

        with pytest.raises(ValueError, match="discarded"):
            buf.seek(2)

    def test_append_after_discard_keeps_appending_at_the_end(self) -> None:
        buf = StreamBuffer()
        buf.append(b"0123")
        buf.read(4)
        buf.discard_consumed()
        buf.append(b"4567")

        assert buf.tell() == 4
        assert buf.read() == b"4567"
        assert buf.tell() == 8

    def test_close_drops_the_buffer(self) -> None:
        buf = StreamBuffer()
        buf.append(b"abc")
        buf.close()
        assert buf.buffered == 0
