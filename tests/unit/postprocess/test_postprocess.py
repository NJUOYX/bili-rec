"""Tests for postprocess module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from birec.postprocess.danmaku_to_ass import DanmakuToAssConfig
from birec.postprocess.metadata import MediaMetadata
from birec.postprocess.models import (
    PostprocessingItem,
    PostprocessingProgress,
    PostprocessingStatus,
)
from birec.postprocess.postprocessor import Postprocessor
from birec.postprocess.remux import parse_ffmpeg_size


class TestPostprocessingModels:
    """Tests for postprocessing models."""

    def test_status_enum(self) -> None:
        assert PostprocessingStatus.WAITING.value == "waiting"
        assert PostprocessingStatus.REMUXING.value == "remuxing"
        assert PostprocessingStatus.INJECTING.value == "injecting"
        assert PostprocessingStatus.COMPLETED.value == "completed"
        assert PostprocessingStatus.FAILED.value == "failed"

    def test_progress_defaults(self) -> None:
        progress = PostprocessingProgress()
        assert progress.status == PostprocessingStatus.WAITING
        assert progress.percent == 0.0
        assert progress.current_size == 0
        assert progress.total_size == 0

    def test_item_is_done(self) -> None:
        item = PostprocessingItem(
            source_path=Path("/tmp/test.flv"),
            output_path=Path("/tmp/test.mp4"),
        )
        assert not item.is_done
        item.status = PostprocessingStatus.COMPLETED
        assert item.is_done
        item.status = PostprocessingStatus.FAILED
        assert item.is_done

    def test_item_defaults(self) -> None:
        item = PostprocessingItem(
            source_path=Path("/tmp/a.flv"),
            output_path=Path("/tmp/a.mp4"),
        )
        assert item.status == PostprocessingStatus.WAITING
        assert item.related_files == []
        assert item.error == ""


class TestMediaMetadata:
    """Tests for MediaMetadata."""

    def test_defaults(self) -> None:
        meta = MediaMetadata()
        assert meta.title == ""
        assert meta.artist == ""

    def test_to_description_json(self) -> None:
        meta = MediaMetadata(title="Test", artist="User")
        json_str = meta.to_description_json()
        assert '"title": "Test"' in json_str
        assert '"artist": "User"' in json_str


class TestDanmakuToAssConfig:
    """Tests for DanmakuToAssConfig."""

    def test_defaults(self) -> None:
        config = DanmakuToAssConfig()
        assert config.font_size == 25
        assert config.sc_font_size == 36
        assert config.resolution_x == 1920
        assert config.resolution_y == 1080

    def test_custom(self) -> None:
        config = DanmakuToAssConfig(font_size=30, resolution_x=1280)
        assert config.font_size == 30
        assert config.resolution_x == 1280


class TestParseFfmpegSize:
    """Tests for parse_ffmpeg_size."""

    def test_parse_valid(self) -> None:
        assert parse_ffmpeg_size("size= 12345kB time=00:01:00") == 12345 * 1024

    def test_parse_no_match(self) -> None:
        assert parse_ffmpeg_size("frame= 100 fps=30") is None

    def test_parse_zero(self) -> None:
        assert parse_ffmpeg_size("size= 0kB") == 0


class TestPostprocessor:
    """Tests for Postprocessor."""

    def test_init_defaults(self) -> None:
        pp = Postprocessor()
        assert not pp.is_running
        assert pp.queue_size == 0
        assert pp.current_item is None

    def test_submit(self) -> None:
        pp = Postprocessor()
        item = pp.submit(Path("/tmp/test.flv"), Path("/tmp/test.mp4"))
        assert pp.queue_size == 1
        assert item.source_path == Path("/tmp/test.flv")
        assert item.status == PostprocessingStatus.WAITING

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        pp = Postprocessor()
        await pp.start()
        assert pp.is_running
        await pp.stop()
        assert not pp.is_running

    @pytest.mark.asyncio
    async def test_process_flv_remux(self, tmp_path) -> None:
        """Test FLV remux with mocked ffmpeg."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv data")
        output = tmp_path / "test.mp4"

        completed_items: list[PostprocessingItem] = []

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=False,
            on_completed=completed_items.append,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await pp.start()
            pp.submit(source, output)
            # Wait for processing
            await asyncio.sleep(0.2)
            await pp.stop()

        assert len(completed_items) == 1
        assert completed_items[0].status == PostprocessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_remux_failure(self, tmp_path) -> None:
        """Test handling of remux failure."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv data")
        output = tmp_path / "test.mp4"

        completed_items: list[PostprocessingItem] = []

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            on_completed=completed_items.append,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await pp.start()
            pp.submit(source, output)
            await asyncio.sleep(0.2)
            await pp.stop()

        assert len(completed_items) == 1
        assert completed_items[0].status == PostprocessingStatus.FAILED

    @pytest.mark.asyncio
    async def test_auto_delete_source(self, tmp_path) -> None:
        """Test AUTO delete strategy removes source on success."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv data")
        output = tmp_path / "test.mp4"
        output.write_bytes(b"fake mp4 data")

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await pp.start()
            pp.submit(source, output)
            await asyncio.sleep(0.2)
            await pp.stop()

        # Source should be deleted (AUTO strategy)
        assert not source.exists()
