"""Tests for danmaku combinator, concatenator, and utilities."""

from __future__ import annotations

import pytest

from birec.danmaku.combinator import DanmakuCombinator, DanmakuConcatenator, TimeBase
from birec.danmaku.models import (
    DanmakuDocument,
    DanmakuItem,
    DanmakuMetadata,
    GiftItem,
    SuperChatItem,
)
from birec.danmaku.reader import DanmakuReader
from birec.danmaku.utils import clear_danmu, copy_danmus, has_danmu, merge_danmaku
from birec.danmaku.writer import DanmakuWriter


class TestDanmakuCombinator:
    """Tests for DanmakuCombinator."""

    def test_combine_empty_list(self) -> None:
        combinator = DanmakuCombinator()
        result = combinator.combine([])
        assert result.document.is_empty()
        assert result.total_added == 0

    def test_combine_single_doc(self) -> None:
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="a"))
        doc.danmakus.append(DanmakuItem(time=2.0, content="b"))

        combinator = DanmakuCombinator()
        result = combinator.combine([doc])
        assert result.total_added == 2
        assert len(result.document.danmakus) == 2

    def test_combine_multiple_docs_sorted(self) -> None:
        doc1 = DanmakuDocument()
        doc1.danmakus.append(DanmakuItem(time=3.0, content="c"))
        doc1.danmakus.append(DanmakuItem(time=1.0, content="a"))

        doc2 = DanmakuDocument()
        doc2.danmakus.append(DanmakuItem(time=2.0, content="b"))

        combinator = DanmakuCombinator()
        result = combinator.combine([doc1, doc2])
        assert result.total_added == 3
        times = [d.time for d in result.document.danmakus]
        assert times == [1.0, 2.0, 3.0]

    def test_combine_preserves_metadata_from_first(self) -> None:
        doc1 = DanmakuDocument(metadata=DanmakuMetadata(recorder="birec"))
        doc2 = DanmakuDocument(metadata=DanmakuMetadata(recorder="other"))

        combinator = DanmakuCombinator()
        result = combinator.combine([doc1, doc2])
        assert result.document.metadata is not None
        assert result.document.metadata.recorder == "birec"

    def test_combine_merges_all_types(self) -> None:
        doc1 = DanmakuDocument()
        doc1.danmakus.append(DanmakuItem(time=1.0, content="d"))
        doc1.super_chats.append(
            SuperChatItem(time=2.0, uid=1, user="u", price=30, content="sc")
        )

        doc2 = DanmakuDocument()
        doc2.gifts.append(GiftItem(time=3.0, uid=1, user="u", gift_name="g"))

        combinator = DanmakuCombinator()
        result = combinator.combine([doc1, doc2])
        assert len(result.document.danmakus) == 1
        assert len(result.document.super_chats) == 1
        assert len(result.document.gifts) == 1

    def test_time_base_property(self) -> None:
        combinator = DanmakuCombinator(TimeBase.LIVE)
        assert combinator.time_base == TimeBase.LIVE


class TestDanmakuConcatenator:
    """Tests for DanmakuConcatenator."""

    def test_concatenate_empty_list(self) -> None:
        concat = DanmakuConcatenator()
        result = concat.concatenate([])
        assert result.document.is_empty()

    def test_concatenate_single_doc(self) -> None:
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="a"))
        doc.danmakus.append(DanmakuItem(time=5.0, content="b"))

        concat = DanmakuConcatenator()
        result = concat.concatenate([doc])
        assert result.total_added == 2
        # Single doc: no offset
        assert result.document.danmakus[0].time == 1.0
        assert result.document.danmakus[1].time == 5.0

    def test_concatenate_with_auto_duration(self) -> None:
        doc1 = DanmakuDocument()
        doc1.danmakus.append(DanmakuItem(time=1.0, content="a"))
        doc1.danmakus.append(DanmakuItem(time=10.0, content="b"))

        doc2 = DanmakuDocument()
        doc2.danmakus.append(DanmakuItem(time=0.5, content="c"))
        doc2.danmakus.append(DanmakuItem(time=3.0, content="d"))

        concat = DanmakuConcatenator()
        result = concat.concatenate([doc1, doc2])

        # doc1 duration = 10.0 (max time)
        # doc2 items offset by 10.0
        assert result.document.danmakus[0].time == 1.0
        assert result.document.danmakus[1].time == 10.0
        assert result.document.danmakus[2].time == pytest.approx(10.5)
        assert result.document.danmakus[3].time == pytest.approx(13.0)

    def test_concatenate_with_explicit_durations(self) -> None:
        doc1 = DanmakuDocument()
        doc1.danmakus.append(DanmakuItem(time=1.0, content="a"))

        doc2 = DanmakuDocument()
        doc2.danmakus.append(DanmakuItem(time=1.0, content="b"))

        concat = DanmakuConcatenator()
        result = concat.concatenate([doc1, doc2], durations=[60.0, 60.0])

        assert result.document.danmakus[0].time == 1.0
        assert result.document.danmakus[1].time == pytest.approx(61.0)

    def test_concatenate_offsets_all_types(self) -> None:
        doc1 = DanmakuDocument()
        doc1.danmakus.append(DanmakuItem(time=5.0, content="a"))

        doc2 = DanmakuDocument()
        doc2.super_chats.append(
            SuperChatItem(time=1.0, uid=1, user="u", price=30, content="sc")
        )
        doc2.gifts.append(GiftItem(time=2.0, uid=1, user="u", gift_name="g"))

        concat = DanmakuConcatenator()
        result = concat.concatenate([doc1, doc2], durations=[10.0, 10.0])

        assert result.document.super_chats[0].time == pytest.approx(11.0)
        assert result.document.gifts[0].time == pytest.approx(12.0)


class TestDanmakuUtils:
    """Tests for danmaku utility functions."""

    def _write_doc(self, path, doc) -> None:
        writer = DanmakuWriter()
        writer.write(doc, path)

    def test_has_danmu_true(self, tmp_path) -> None:
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="hello"))
        path = tmp_path / "test.xml"
        self._write_doc(path, doc)
        assert has_danmu(path) is True

    def test_has_danmu_false_empty(self, tmp_path) -> None:
        doc = DanmakuDocument()
        path = tmp_path / "test.xml"
        self._write_doc(path, doc)
        assert has_danmu(path) is False

    def test_has_danmu_false_not_exists(self, tmp_path) -> None:
        assert has_danmu(tmp_path / "nope.xml") is False

    def test_clear_danmu(self, tmp_path) -> None:
        doc = DanmakuDocument(metadata=DanmakuMetadata(recorder="birec", room_id=123))
        doc.danmakus.append(DanmakuItem(time=1.0, content="hello"))
        doc.danmakus.append(DanmakuItem(time=2.0, content="world"))
        path = tmp_path / "test.xml"
        self._write_doc(path, doc)

        clear_danmu(path)

        reader = DanmakuReader()
        cleared = reader.read(path)
        assert cleared.is_empty()
        assert cleared.metadata is not None
        assert cleared.metadata.recorder == "birec"

    def test_clear_danmu_nonexistent(self, tmp_path) -> None:
        # Should not raise
        clear_danmu(tmp_path / "nope.xml")

    def test_copy_danmus(self, tmp_path) -> None:
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="hello"))
        src = tmp_path / "src.xml"
        dst = tmp_path / "sub" / "dst.xml"
        self._write_doc(src, doc)

        copy_danmus(src, dst)
        assert dst.exists()

        reader = DanmakuReader()
        loaded = reader.read(dst)
        assert len(loaded.danmakus) == 1

    def test_copy_danmus_nonexistent_src(self, tmp_path) -> None:
        # Should not raise
        copy_danmus(tmp_path / "nope.xml", tmp_path / "dst.xml")

    def test_merge_danmaku_append(self, tmp_path) -> None:
        src_doc = DanmakuDocument()
        src_doc.danmakus.append(DanmakuItem(time=5.0, content="from_src"))

        dst_doc = DanmakuDocument()
        dst_doc.danmakus.append(DanmakuItem(time=1.0, content="from_dst"))

        src = tmp_path / "src.xml"
        dst = tmp_path / "dst.xml"
        self._write_doc(src, src_doc)
        self._write_doc(dst, dst_doc)

        count = merge_danmaku(src, dst)
        assert count == 1

        reader = DanmakuReader()
        merged = reader.read(dst)
        assert len(merged.danmakus) == 2
        # dst first, then src (append mode)
        assert merged.danmakus[0].content == "from_dst"
        assert merged.danmakus[1].content == "from_src"

        # src should be cleared
        src_after = reader.read(src)
        assert src_after.is_empty()

    def test_merge_danmaku_prepend(self, tmp_path) -> None:
        src_doc = DanmakuDocument()
        src_doc.danmakus.append(DanmakuItem(time=0.5, content="from_src"))

        dst_doc = DanmakuDocument()
        dst_doc.danmakus.append(DanmakuItem(time=1.0, content="from_dst"))

        src = tmp_path / "src.xml"
        dst = tmp_path / "dst.xml"
        self._write_doc(src, src_doc)
        self._write_doc(dst, dst_doc)

        count = merge_danmaku(src, dst, prepend=True)
        assert count == 1

        reader = DanmakuReader()
        merged = reader.read(dst)
        assert len(merged.danmakus) == 2
        # src first (prepend mode)
        assert merged.danmakus[0].content == "from_src"
        assert merged.danmakus[1].content == "from_dst"

    def test_merge_danmaku_src_not_exists(self, tmp_path) -> None:
        dst = tmp_path / "dst.xml"
        count = merge_danmaku(tmp_path / "nope.xml", dst)
        assert count == 0

    def test_merge_danmaku_src_empty(self, tmp_path) -> None:
        src = tmp_path / "src.xml"
        dst = tmp_path / "dst.xml"
        self._write_doc(src, DanmakuDocument())
        self._write_doc(dst, DanmakuDocument())

        count = merge_danmaku(src, dst)
        assert count == 0

    def test_merge_danmaku_dst_not_exists(self, tmp_path) -> None:
        src_doc = DanmakuDocument()
        src_doc.danmakus.append(DanmakuItem(time=1.0, content="hello"))
        src = tmp_path / "src.xml"
        dst = tmp_path / "new_dst.xml"
        self._write_doc(src, src_doc)

        count = merge_danmaku(src, dst)
        assert count == 1
        assert dst.exists()
