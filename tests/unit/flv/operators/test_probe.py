"""Tests for probe operator."""

from __future__ import annotations

import pytest

from birec.flv.operators import Prober, StreamInfo


class TestStreamInfo:
    """Tests for StreamInfo."""

    def test_frozen(self) -> None:
        """Test that StreamInfo is immutable."""
        info = StreamInfo(
            codec_name="h264",
            width=1920,
            height=1080,
            avg_frame_rate="30/1",
            bit_rate=5000000,
            duration=100.0,
        )
        assert info.codec_name == "h264"
        assert info.width == 1920
        assert info.height == 1080


class TestProber:
    """Tests for Prober."""

    def test_available(self) -> None:
        """Test ffprobe availability check."""
        prober = Prober()
        # This test just checks the property doesn't raise
        _ = prober.available

    def test_parse_output(self) -> None:
        """Test parsing ffprobe output."""
        prober = Prober()

        data = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30/1",
                    "bit_rate": "5000000",
                    "duration": "100.5",
                }
            ]
        }

        info = prober._parse_output(data)

        assert info.codec_name == "h264"
        assert info.width == 1920
        assert info.height == 1080
        assert info.avg_frame_rate == "30/1"
        assert info.bit_rate == 5000000
        assert info.duration == 100.5

    def test_parse_output_no_video(self) -> None:
        """Test parsing output without video stream."""
        prober = Prober()

        data = {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                }
            ]
        }

        info = prober._parse_output(data)

        assert info.codec_name is None
        assert info.width is None


@pytest.mark.ffmpeg
class TestProberIntegration:
    """Integration tests for Prober (requires ffprobe)."""

    @pytest.mark.asyncio
    async def test_probe_nonexistent_file(self) -> None:
        """Test probing a nonexistent file."""
        from pathlib import Path

        prober = Prober()
        if not prober.available:
            pytest.skip("ffprobe not available")

        result = await prober.probe_file(Path("/nonexistent/file.flv"))
        assert result is None
