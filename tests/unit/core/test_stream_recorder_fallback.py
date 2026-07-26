"""Tests for StreamRecorder FLV<->fMP4 fallback orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birec.core.stream_recorder import StreamRecorder

pytestmark = pytest.mark.unit


@pytest.fixture
def recorder() -> StreamRecorder:
    """Create a StreamRecorder with mocked dependencies."""
    return StreamRecorder(
        live=MagicMock(),
        session=MagicMock(),
        path_provider=MagicMock(),
        metadata_provider=MagicMock(),
    )


def _scripted(results: list[bool]) -> Callable[[], Awaitable[bool]]:
    """Build an async availability checker returning scripted values."""
    iterator = iter(results)

    async def check() -> bool:
        return next(iterator)

    return check


async def _always_false() -> bool:
    return False


class TestResolveStreamFormat:
    def test_preferred_flv_available(self, recorder: StreamRecorder) -> None:
        recorder.stream_params.stream_format = "flv"
        assert (
            recorder.resolve_stream_format(flv_available=True, fmp4_available=True)
            == "flv"
        )

    def test_preferred_flv_unavailable_falls_back_to_fmp4(
        self, recorder: StreamRecorder
    ) -> None:
        recorder.stream_params.stream_format = "flv"
        assert (
            recorder.resolve_stream_format(flv_available=False, fmp4_available=True)
            == "fmp4"
        )

    def test_preferred_fmp4_available(self, recorder: StreamRecorder) -> None:
        recorder.stream_params.stream_format = "fmp4"
        assert (
            recorder.resolve_stream_format(flv_available=True, fmp4_available=True)
            == "fmp4"
        )

    def test_preferred_fmp4_unavailable_falls_back_to_flv(
        self, recorder: StreamRecorder
    ) -> None:
        recorder.stream_params.stream_format = "fmp4"
        assert (
            recorder.resolve_stream_format(flv_available=True, fmp4_available=False)
            == "flv"
        )


class TestWaitForFmp4Stream:
    async def test_available_immediately(self, recorder: StreamRecorder) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result = await recorder.wait_for_fmp4_stream(
            _scripted([True]),
            timeout=10,
            interval=1,
            sleep=fake_sleep,
        )
        assert result is True
        assert sleeps == []  # no waiting needed

    async def test_available_after_delay(self, recorder: StreamRecorder) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result = await recorder.wait_for_fmp4_stream(
            _scripted([False, False, True]),
            timeout=10,
            interval=1,
            sleep=fake_sleep,
        )
        assert result is True
        assert sleeps == [1, 1]  # waited twice before availability

    async def test_timeout_falls_back(self, recorder: StreamRecorder) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result = await recorder.wait_for_fmp4_stream(
            _always_false,
            timeout=3,
            interval=1,
            sleep=fake_sleep,
        )
        assert result is False
        assert sleeps == [1, 1, 1]  # waited until timeout


class TestRealStreamTracking:
    def test_mark_stream_available_records_format_and_quality(
        self, recorder: StreamRecorder
    ) -> None:
        assert recorder.real_stream_format is None
        assert recorder.stream_available_time is None

        recorder.mark_stream_available(stream_format="flv", quality_number=10000)

        assert recorder.real_stream_format == "flv"
        assert recorder.real_quality_number == 10000
        assert recorder.stream_available_time is not None

    def test_available_time_preserved_across_hot_swap(
        self, recorder: StreamRecorder
    ) -> None:
        recorder.mark_stream_available(stream_format="fmp4")
        first_time = recorder.stream_available_time
        assert first_time is not None

        # Hot-swap to flv: format updates, timestamp preserved.
        recorder.mark_stream_available(stream_format="flv")
        assert recorder.real_stream_format == "flv"
        assert recorder.stream_available_time is first_time

    @pytest.mark.asyncio
    async def test_start_recording_resets_tracking(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        recorder._path_provider.video_path.return_value = str(tmp_path / "v.flv")
        recorder._path_provider.meta_path.return_value = str(tmp_path / "v.meta")
        recorder._metadata_provider.build_ffmpeg_metadata.return_value = "meta"

        recorder.mark_stream_available(stream_format="flv", quality_number=400)
        assert recorder.real_stream_format == "flv"

        await recorder.start_recording()

        assert recorder.real_stream_format is None
        assert recorder.real_quality_number is None
        assert recorder.stream_available_time is None
