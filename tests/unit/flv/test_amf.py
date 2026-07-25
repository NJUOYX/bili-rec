"""Tests for AMF0 encoding/decoding."""

from __future__ import annotations

from io import BytesIO

from birec.flv import amf


class TestAMF0Number:
    """Tests for AMF0 Number."""

    def test_round_trip(self) -> None:
        value = 123.456
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value

    def test_integer(self) -> None:
        value = 42
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == 42.0

    def test_negative(self) -> None:
        value = -123.456
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value


class TestAMF0Boolean:
    """Tests for AMF0 Boolean."""

    def test_true(self) -> None:
        data = amf.dumps(True)
        result = amf.loads(data)
        assert result is True

    def test_false(self) -> None:
        data = amf.dumps(False)
        result = amf.loads(data)
        assert result is False


class TestAMF0String:
    """Tests for AMF0 String."""

    def test_simple(self) -> None:
        value = "hello"
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value

    def test_unicode(self) -> None:
        value = "你好世界"
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value

    def test_empty(self) -> None:
        value = ""
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value


class TestAMF0Object:
    """Tests for AMF0 Object."""

    def test_simple(self) -> None:
        value = {"name": "test", "value": 123}
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value

    def test_nested(self) -> None:
        value = {"outer": {"inner": "value"}}
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value

    def test_empty(self) -> None:
        value: dict[str, object] = {}
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == value


class TestAMF0Null:
    """Tests for AMF0 Null."""

    def test_none(self) -> None:
        data = amf.dumps(None)
        result = amf.loads(data)
        assert result is None


class TestAMF0Array:
    """Tests for AMF0 Array."""

    def test_simple(self) -> None:
        value = [1, 2, 3]
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == [1.0, 2.0, 3.0]

    def test_mixed(self) -> None:
        value = [1, "two", True]
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == [1.0, "two", True]


class TestAMF0ECMAArray:
    """Tests for AMF0 ECMA Array."""

    def test_round_trip(self) -> None:
        value = amf.AMF0ECMAArray({"key": "value", "num": 42})
        data = amf.dumps(value)
        result = amf.loads(data)
        assert result == {"key": "value", "num": 42.0}


class TestAMF0Date:
    """Tests for AMF0 Date."""

    def test_round_trip(self) -> None:
        value = amf.AMF0Date(1234567890.0, 0)
        data = amf.dumps(value)
        result = amf.loads(data)
        assert isinstance(result, amf.AMF0Date)
        assert result.value == value.value
        assert result.timezone == value.timezone


class TestAMF0Stream:
    """Tests for stream-based operations."""

    def test_multiple_values(self) -> None:
        stream = BytesIO()
        amf.dump("name", stream)
        amf.dump({"key": "value"}, stream)

        stream.seek(0)
        name = amf.load(stream)
        obj = amf.load(stream)

        assert name == "name"
        assert obj == {"key": "value"}
