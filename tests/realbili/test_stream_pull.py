"""Real stream pull and FLV product validation.

Resolves the FLV stream URL for a live room, verifies CDN connectivity, pulls a
small prefix of the live stream, and validates that the captured bytes form a
well-formed FLV file (header signature + parseable tags) using the birec FLV
reader. Skips gracefully when the room is not live or offers no FLV stream.
"""

from __future__ import annotations

import io
from pathlib import Path

import aiohttp
import pytest

from birec.bili.exceptions import NoStreamFormatAvailable
from birec.bili.live import Live
from birec.bili.models import LiveStatus
from birec.flv.io import FlvReader

# ~512 KiB comfortably covers the FLV header plus the first several tags
# (metadata + AVC/AAC sequence headers) without waiting on a large download.
_PULL_BYTES = 512 * 1024
_PULL_TIMEOUT = 20.0


async def _require_live_flv_url(live: Live) -> str:
    status = await live.get_live_status()
    if status != LiveStatus.LIVE:
        pytest.skip(f"room {live.room_id} is not LIVE (status={status.name})")
    try:
        return await live.get_stream_url("flv")
    except NoStreamFormatAvailable:
        pytest.skip(f"room {live.room_id} offers no FLV stream")


class TestStreamPull:
    async def test_flv_url_resolves_and_is_reachable(self, live: Live) -> None:
        url = await _require_live_flv_url(live)
        assert url.startswith("http")
        assert await live.test_connectivity(url), f"stream URL unreachable: {url}"

    async def test_pulled_bytes_are_valid_flv(
        self,
        live: Live,
        bili_session: aiohttp.ClientSession,
        tmp_path: Path,
    ) -> None:
        url = await _require_live_flv_url(live)

        buf = bytearray()
        async with bili_session.get(
            url,
            headers=live.api.headers,
            timeout=aiohttp.ClientTimeout(total=_PULL_TIMEOUT),
        ) as res:
            assert res.status == 200
            async for chunk in res.content.iter_chunked(64 * 1024):
                buf.extend(chunk)
                if len(buf) >= _PULL_BYTES:
                    break

        assert buf[:3] == b"FLV", "pulled data does not start with an FLV signature"

        # Persist the captured fragment as a recording product and re-open it.
        out_file = tmp_path / f"{live.room_id}.flv"
        out_file.write_bytes(bytes(buf))
        assert out_file.stat().st_size > 3

        reader = FlvReader(io.BytesIO(bytes(buf)))
        header = reader.read_header()
        assert header.signature == "FLV"

        tags = []
        for tag in reader.read_tags():
            tags.append(tag)
            if len(tags) >= 3:
                break
        assert tags, "no FLV tags could be parsed from the pulled stream"
