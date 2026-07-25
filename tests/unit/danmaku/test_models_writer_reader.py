"""Tests for danmaku models, writer, and reader."""

from __future__ import annotations

import pytest

from birec.danmaku.models import (
    DanmakuDocument,
    DanmakuItem,
    DanmakuMetadata,
    GiftItem,
    GuardItem,
    SuperChatItem,
    ToastItem,
)
from birec.danmaku.reader import DanmakuReader
from birec.danmaku.writer import DanmakuWriter


class TestDanmakuModels:
    """Tests for danmaku data models."""

    def test_danmaku_item_defaults(self) -> None:
        item = DanmakuItem(time=1.5, content="hello")
        assert item.time == 1.5
        assert item.content == "hello"
        assert item.mode == 1
        assert item.font_size == 25
        assert item.color == 16777215
        assert item.timestamp == 0
        assert item.pool == 0
        assert item.uid == 0
        assert item.row_id == 0

    def test_danmaku_item_frozen(self) -> None:
        item = DanmakuItem(time=1.0, content="test")
        with pytest.raises(AttributeError):
            item.time = 2.0  # type: ignore[misc]

    def test_super_chat_item(self) -> None:
        sc = SuperChatItem(time=5.0, uid=123, user="user1", price=30, content="SC!")
        assert sc.time == 5.0
        assert sc.uid == 123
        assert sc.price == 30

    def test_gift_item_coin_type(self) -> None:
        gift = GiftItem(time=2.0, uid=1, user="u", gift_name="辣条", coin_type="gold")
        assert gift.coin_type == "gold"

    def test_guard_item(self) -> None:
        guard = GuardItem(time=3.0, uid=1, user="u", level=3, num=1, price=198000)
        assert guard.level == 3
        assert guard.price == 198000

    def test_toast_item(self) -> None:
        toast = ToastItem(time=4.0, uid=1, user="u", message="欢迎")
        assert toast.message == "欢迎"

    def test_document_total_count(self) -> None:
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="a"))
        doc.danmakus.append(DanmakuItem(time=2.0, content="b"))
        doc.super_chats.append(
            SuperChatItem(time=3.0, uid=1, user="u", price=30, content="sc")
        )
        assert doc.total_count == 3

    def test_document_is_empty(self) -> None:
        doc = DanmakuDocument()
        assert doc.is_empty()
        doc.danmakus.append(DanmakuItem(time=1.0, content="x"))
        assert not doc.is_empty()

    def test_metadata(self) -> None:
        meta = DanmakuMetadata(recorder="birec", room_id=12345, user_name="test_user")
        assert meta.recorder == "birec"
        assert meta.room_id == 12345


class TestDanmakuWriter:
    """Tests for DanmakuWriter."""

    def test_write_empty_document(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert '<?xml version="1.0" encoding="utf-8"?>' in content
        assert "<i>" in content
        assert "</i>" in content

    def test_write_with_metadata(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument(
            metadata=DanmakuMetadata(recorder="birec", room_id=12345, user_name="test")
        )
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "<metadata>" in content
        assert "<recorder>birec</recorder>" in content
        assert "<room_id>12345</room_id>" in content

    def test_write_danmaku_item(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.5, content="hello", mode=1, uid=100))
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert '<d p="1.50000,1,25,16777215,0,0,100,0">hello</d>' in content

    def test_write_escapes_xml(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="<script>&test</script>"))
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "&lt;script&gt;" in content
        assert "&amp;test" in content

    def test_write_cleans_control_chars(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.danmakus.append(DanmakuItem(time=1.0, content="hello\x00world\x01!"))
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "helloworld!" in content
        assert "\x00" not in content

    def test_write_super_chat(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.super_chats.append(
            SuperChatItem(time=5.0, uid=1, user="u", price=30, content="SC", sc_id=99)
        )
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "<sc " in content
        assert 'price="30"' in content

    def test_write_gift(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.gifts.append(
            GiftItem(
                time=2.0,
                uid=1,
                user="u",
                gift_name="辣条",
                coin_type="gold",
                num=5,
            )
        )
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "<gift " in content
        assert 'coin_type="gold"' in content
        assert 'num="5"' in content

    def test_write_guard(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.guards.append(GuardItem(time=3.0, uid=1, user="u", level=3))
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "<guard " in content
        assert 'level="3"' in content

    def test_write_toast(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        doc.toasts.append(ToastItem(time=4.0, uid=1, user="u", message="欢迎"))
        path = tmp_path / "test.xml"
        writer.write(doc, path)

        content = path.read_text(encoding="utf-8")
        assert "<toast " in content
        assert "欢迎" in content

    def test_write_creates_parent_dirs(self, tmp_path) -> None:
        writer = DanmakuWriter()
        doc = DanmakuDocument()
        path = tmp_path / "sub" / "dir" / "test.xml"
        writer.write(doc, path)
        assert path.exists()


class TestDanmakuReader:
    """Tests for DanmakuReader."""

    def test_read_empty_file(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<i>\n</i>\n',
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert doc.is_empty()

    def test_read_file_not_found(self, tmp_path) -> None:
        reader = DanmakuReader()
        with pytest.raises(FileNotFoundError):
            reader.read(tmp_path / "nonexistent.xml")

    def test_read_malformed_xml(self, tmp_path) -> None:
        path = tmp_path / "bad.xml"
        path.write_text("not xml at all", encoding="utf-8")
        reader = DanmakuReader()
        with pytest.raises(ValueError, match="Failed to parse"):
            reader.read(path)

    def test_read_danmaku_items(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <d p="1.50000,1,25,16777215,1700000000,0,123,0">hello</d>\n'
            '  <d p="2.00000,5,18,255,1700000001,0,456,0">world</d>\n'
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.danmakus) == 2
        assert doc.danmakus[0].time == 1.5
        assert doc.danmakus[0].content == "hello"
        assert doc.danmakus[0].uid == 123
        assert doc.danmakus[1].mode == 5
        assert doc.danmakus[1].color == 255

    def test_read_metadata(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            "  <metadata>\n"
            "    <recorder>birec</recorder>\n"
            "    <room_id>12345</room_id>\n"
            "    <user_name>test_user</user_name>\n"
            "  </metadata>\n"
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert doc.metadata is not None
        assert doc.metadata.recorder == "birec"
        assert doc.metadata.room_id == 12345
        assert doc.metadata.user_name == "test_user"

    def test_read_super_chat(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <sc ts="5.00000" uid="123" user="user1" price="30" id="99">SC!</sc>\n'
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.super_chats) == 1
        assert doc.super_chats[0].price == 30
        assert doc.super_chats[0].content == "SC!"

    def test_read_gift(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <gift ts="2.00000" uid="1" user="u" giftname="辣条"'
            ' giftid="100" num="5" price="100" coin_type="gold" action="投喂"/>\n'
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.gifts) == 1
        assert doc.gifts[0].gift_name == "辣条"
        assert doc.gifts[0].coin_type == "gold"
        assert doc.gifts[0].num == 5

    def test_read_guard(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <guard ts="3.00000" uid="1" user="u"'
            ' level="3" num="1" price="198000"/>\n'
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.guards) == 1
        assert doc.guards[0].level == 3

    def test_read_toast(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <toast ts="4.00000" uid="1" user="u">欢迎</toast>\n'
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.toasts) == 1
        assert doc.toasts[0].message == "欢迎"

    def test_read_skips_invalid_danmaku(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i>\n"
            '  <d p="invalid">bad</d>\n'
            '  <d p="1.0,1,25,16777215">good</d>\n'
            "  <d>no params</d>\n"
            "</i>\n",
            encoding="utf-8",
        )
        reader = DanmakuReader()
        doc = reader.read(path)
        assert len(doc.danmakus) == 1
        assert doc.danmakus[0].content == "good"


class TestRoundTrip:
    """Test write → read round trip."""

    def test_round_trip_full_document(self, tmp_path) -> None:
        writer = DanmakuWriter()
        reader = DanmakuReader()

        doc = DanmakuDocument(
            metadata=DanmakuMetadata(
                recorder="birec", room_id=999, user_name="streamer"
            )
        )
        doc.danmakus.append(DanmakuItem(time=1.0, content="first", uid=10))
        doc.danmakus.append(DanmakuItem(time=2.0, content="second", uid=20))
        doc.super_chats.append(
            SuperChatItem(time=3.0, uid=30, user="sc_user", price=50, content="SC")
        )
        doc.gifts.append(GiftItem(time=4.0, uid=40, user="gift_user", gift_name="火箭"))
        doc.guards.append(GuardItem(time=5.0, uid=50, user="guard_user", level=2))
        doc.toasts.append(ToastItem(time=6.0, uid=60, user="toast_user", message="hi"))

        path = tmp_path / "roundtrip.xml"
        writer.write(doc, path)
        loaded = reader.read(path)

        assert loaded.metadata is not None
        assert loaded.metadata.recorder == "birec"
        assert loaded.metadata.room_id == 999
        assert len(loaded.danmakus) == 2
        assert loaded.danmakus[0].content == "first"
        assert loaded.danmakus[1].uid == 20
        assert len(loaded.super_chats) == 1
        assert loaded.super_chats[0].price == 50
        assert len(loaded.gifts) == 1
        assert loaded.gifts[0].gift_name == "火箭"
        assert len(loaded.guards) == 1
        assert loaded.guards[0].level == 2
        assert len(loaded.toasts) == 1
        assert loaded.toasts[0].message == "hi"
