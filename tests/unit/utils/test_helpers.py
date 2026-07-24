import hashlib
import zlib

import pytest

from birec.utils.hash import cksum, md5sum, sha1sum
from birec.utils.io import wait_for
from birec.utils.patterns import Singleton
from birec.utils.string import (
    camel_case,
    extract_buvid_from_cookie,
    extract_uid_from_cookie,
    snake_case,
)
from birec.utils.url import ensure_scheme


@pytest.mark.parametrize(
    ("value", "expected"),
    [("roomId", "room_id"), ("baseApiUrls", "base_api_urls"), ("plain", "plain")],
)
def test_snake_case(value: str, expected: str) -> None:
    assert snake_case(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("room_id", "roomId"), ("base_api_urls", "baseApiUrls"), ("plain", "plain")],
)
def test_camel_case(value: str, expected: str) -> None:
    assert camel_case(value) == expected


def test_case_roundtrip() -> None:
    assert snake_case(camel_case("base_api_urls")) == "base_api_urls"


def test_extract_uid_from_cookie() -> None:
    assert extract_uid_from_cookie("DedeUserID=12345; foo=bar") == 12345
    assert extract_uid_from_cookie("no uid here") is None


def test_extract_buvid_from_cookie() -> None:
    assert extract_buvid_from_cookie("buvid3=abc-DEF_123; x=1") == "abc-DEF_123"
    assert extract_buvid_from_cookie("nope") is None


def test_ensure_scheme() -> None:
    assert ensure_scheme("http://a.com/x", "https") == "https://a.com/x"
    assert ensure_scheme("https://a.com/x", "http") == "http://a.com/x"


def test_cksum_bytes_matches_zlib() -> None:
    data = b"hello world"
    assert cksum(data) == format(zlib.crc32(data) & 0xFFFFFFFF, "x")


def test_md5_sha1_bytes_match_hashlib() -> None:
    data = b"hello world"
    assert md5sum(data) == hashlib.md5(data).hexdigest()
    assert sha1sum(data) == hashlib.sha1(data).hexdigest()


def test_hash_file_equals_bytes(tmp_path) -> None:
    data = b"a" * 20000
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    assert cksum(str(path)) == cksum(data)
    assert md5sum(str(path)) == md5sum(data)
    assert sha1sum(str(path)) == sha1sum(data)


def test_singleton_returns_same_instance() -> None:
    class Foo(Singleton):
        def __init__(self) -> None:
            self.value = 1

    assert Foo.get_instance() is Foo.get_instance()


def test_singleton_abstract_rejected() -> None:
    with pytest.raises(TypeError):
        Singleton.get_instance()


def test_wait_for_returns_result() -> None:
    assert wait_for(lambda x: x + 1, args=(1,), timeout=1.0) == 2


def test_wait_for_times_out() -> None:
    import time

    with pytest.raises(TimeoutError):
        wait_for(lambda: time.sleep(1.0), timeout=0.05)
