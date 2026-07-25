"""High-level FLV reader and writer."""

from __future__ import annotations

from collections.abc import Iterator
from io import SEEK_CUR

from .exceptions import FlvDataError
from .format import FlvDumper, FlvParser
from .models import BACK_POINTER_SIZE, FlvHeader, FlvTag
from .struct_io import RandomIO
from .utils import AutoRollbacker, OffsetRepositor

__all__ = ("FlvReader", "FlvWriter")


class FlvReader:
    """Read FLV data from a stream."""

    def __init__(
        self,
        stream: RandomIO,
        *,
        backup_timestamp: bool = False,
        restore_timestamp: bool = False,
    ) -> None:
        self._stream = stream
        self._backup_timestamp = backup_timestamp
        self._restore_timestamp = restore_timestamp
        self._parser = FlvParser(
            stream,
            backup_timestamp=backup_timestamp,
            restore_timestamp=restore_timestamp,
        )

    def read_header(self) -> FlvHeader:
        """Read and validate FLV header."""
        header = self._parser.parse_header()
        previous_tag_size = self._parser.parse_previous_tag_size()
        if previous_tag_size != 0:
            raise FlvDataError(f"First back-pointer must be 0: {previous_tag_size}")
        return header

    def read_tag(self, *, no_body: bool = False) -> FlvTag:
        """Read a single tag with back-pointer validation."""
        tag = self._parser.parse_tag(no_body=no_body)
        previous_tag_size = self._parser.parse_previous_tag_size()
        if previous_tag_size != tag.tag_size:
            raise FlvDataError(f"Wrong back-pointer: {previous_tag_size}")
        return tag

    def read_tags(self, *, no_body: bool = False) -> Iterator[FlvTag]:
        """Read all tags until EOF."""
        while True:
            try:
                yield self.read_tag(no_body=no_body)
            except EOFError:
                break

    def rread_tag(self, *, no_body: bool = False) -> FlvTag:
        """Read previous tag (reverse read)."""
        self._seek_to_previous_tag()
        with OffsetRepositor(self._stream):
            return self.read_tag(no_body=no_body)

    def rread_tags(self, *, no_body: bool = False) -> Iterator[FlvTag]:
        """Read tags in reverse until beginning."""
        while True:
            try:
                yield self.rread_tag(no_body=no_body)
            except EOFError:
                break

    def read_body(self, tag: FlvTag) -> bytes:
        """Read the body of a tag (for no_body reads)."""
        with OffsetRepositor(self._stream):
            self._stream.seek(tag.body_offset)
            return self._stream.read(tag.body_size)

    def _seek_to_previous_tag(self) -> int:
        """Seek to the beginning of the previous tag."""
        try:
            self._stream.seek(-BACK_POINTER_SIZE, SEEK_CUR)
        except OSError as e:
            if e.errno == 22 and e.strerror == "Invalid argument":
                raise EOFError from e
            raise
        previous_tag_size = self._parser.parse_previous_tag_size()
        return self._stream.seek(-(4 + previous_tag_size), SEEK_CUR)


class FlvWriter:
    """Write FLV data to a stream."""

    def __init__(self, stream: RandomIO) -> None:
        self._stream = stream
        self._dumper = FlvDumper(stream)

    def write_header(self, header: FlvHeader) -> int:
        """Write FLV header and initial back-pointer."""
        with AutoRollbacker(self._stream):
            self._dumper.dump_header(header)
            self._dumper.dump_previous_tag_size(0)
            return header.size + BACK_POINTER_SIZE

    def write_tag(self, tag: FlvTag) -> int:
        """Write a tag with back-pointer."""
        with AutoRollbacker(self._stream):
            self._dumper.dump_tag(tag)
            self._dumper.dump_previous_tag_size(tag.tag_size)
            return tag.tag_size + BACK_POINTER_SIZE

    def write_tags(self, tags: list[FlvTag] | tuple[FlvTag, ...]) -> int:
        """Write multiple tags."""
        return sum(self.write_tag(tag) for tag in tags)
