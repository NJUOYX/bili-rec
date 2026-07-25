"""Tests for birec.bili.wbi (WBI signing algorithm)."""

from __future__ import annotations

from birec.bili.wbi import build_query, encode_value, extract_key, make_key

IMG_KEY = "7cd084941338484aae1ad9425b84077c"
SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"
MIXED_KEY = "ea1db124af3c7062474693fa704f4ff8"


class TestExtractKey:
    def test_png_url(self) -> None:
        url = "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png"
        assert extract_key(url) == IMG_KEY

    def test_no_extension(self) -> None:
        assert extract_key("https://example.com/abc123") == "abc123"


class TestMakeKey:
    def test_known_pair(self) -> None:
        assert make_key(IMG_KEY, SUB_KEY) == MIXED_KEY

    def test_deterministic(self) -> None:
        assert make_key(IMG_KEY, SUB_KEY) == make_key(IMG_KEY, SUB_KEY)


class TestEncodeValue:
    def test_strips_special_chars(self) -> None:
        assert encode_value(")-_-( F**' 哔~!") == "-_-%20F%20%E5%93%94~"

    def test_unreserved_passthrough(self) -> None:
        assert encode_value("abc-_.~123") == "abc-_.~123"

    def test_empty(self) -> None:
        assert encode_value("") == ""

    def test_all_special_stripped(self) -> None:
        assert encode_value("!'()*") == ""


class TestBuildQuery:
    def test_known_signature(self) -> None:
        ts = 1748867128
        params: list[tuple[str, object]] = [
            ("foo", ")-_-( F**' 哔~!"),
            ("bar", 2333),
        ]
        expected = (
            "bar=2333&foo=-_-%20F%20%E5%93%94~"
            "&wts=1748867128&w_rid=6ba96e28a3f09b40e704f1e4b4f8e3e3"
        )
        assert build_query(MIXED_KEY, ts, params) == expected

    def test_params_sorted_by_key(self) -> None:
        params: list[tuple[str, object]] = [("z", 1), ("a", 2)]
        result = build_query(MIXED_KEY, 100, params)
        assert result.index("a=2") < result.index("z=1")
        assert "wts=100" in result
        assert "w_rid=" in result

    def test_wts_appended(self) -> None:
        params: list[tuple[str, object]] = [("x", "y")]
        result = build_query(MIXED_KEY, 999, params)
        assert "wts=999" in result
