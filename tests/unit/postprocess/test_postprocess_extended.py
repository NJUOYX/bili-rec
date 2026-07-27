"""Extended tests for postprocess module to achieve ≥85% coverage."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.postprocess.danmaku_to_ass import (
    DanmakuToAssConfig,
    convert_danmaku_to_ass,
    find_dmconvert,
)
from birec.postprocess.metadata import MediaMetadata, inject_metadata
from birec.postprocess.models import (
    PostprocessingItem,
    PostprocessingStatus,
)
from birec.postprocess.postprocessor import Postprocessor
from birec.postprocess.remux import (
    _generate_m3u8,
    find_ffmpeg,
    remux_flv_to_mp4,
    remux_fmp4_to_mp4,
)

_FFMPEG = "/usr/bin/ffmpeg"
_REMUX_FIND = "birec.postprocess.remux.find_ffmpeg"
_META_FIND = "birec.postprocess.metadata.find_ffmpeg"
_DM_FIND = "birec.postprocess.danmaku_to_ass.find_dmconvert"
_SUBPROCESS = "asyncio.create_subprocess_exec"

# ── remux.py tests ────────────────────────────────────────────────────────────


class TestFindFfmpeg:
    def test_find_ffmpeg_exists(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert find_ffmpeg() == "/usr/bin/ffmpeg"

    def test_find_ffmpeg_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            assert find_ffmpeg() is None


class TestRemuxFlvToMp4:
    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake")
        output = tmp_path / "test.mp4"

        with patch("birec.postprocess.remux.find_ffmpeg", return_value=None):
            result = await remux_flv_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_source_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "nonexistent.flv"
        output = tmp_path / "test.mp4"

        with patch(_REMUX_FIND, return_value=_FFMPEG):
            result = await remux_flv_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_success(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_flv_to_mp4(source, output)
        assert result is True

    @pytest.mark.asyncio
    async def test_ffmpeg_failure(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error occurred"))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_flv_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_flv_to_mp4(source, output, timeout=0.001)
        assert result is False

    @pytest.mark.asyncio
    async def test_os_error(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                side_effect=OSError("exec failed"),
            ),
        ):
            result = await remux_flv_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_filler_removal(self, tmp_path: Path) -> None:
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ) as mock_exec,
        ):
            result = await remux_flv_to_mp4(source, output, remove_filler=False)
        assert result is True
        # Verify filter_units not in command
        call_args = mock_exec.call_args[0]
        assert "filter_units=remove_types=12" not in call_args


class TestRemuxFmp4ToMp4:
    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake")
        output = tmp_path / "test.mp4"

        with patch("birec.postprocess.remux.find_ffmpeg", return_value=None):
            result = await remux_fmp4_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_source_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "nonexistent.m4s"
        output = tmp_path / "test.mp4"

        with patch(_REMUX_FIND, return_value=_FFMPEG):
            result = await remux_fmp4_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_success_with_generated_m3u8(self, tmp_path: Path) -> None:
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake m4s")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_fmp4_to_mp4(source, output)
        assert result is True

    @pytest.mark.asyncio
    async def test_success_with_existing_m3u8(self, tmp_path: Path) -> None:
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake m4s")
        m3u8 = tmp_path / "test.m3u8"
        m3u8.write_text("#EXTM3U\n#EXTINF:10,\ntest.m4s\n")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_fmp4_to_mp4(source, output, m3u8_path=m3u8)
        assert result is True

    @pytest.mark.asyncio
    async def test_ffmpeg_failure(self, tmp_path: Path) -> None:
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake m4s")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_fmp4_to_mp4(source, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path) -> None:
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake m4s")
        output = tmp_path / "test.mp4"

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with (
            patch(_REMUX_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await remux_fmp4_to_mp4(source, output, timeout=0.001)
        assert result is False


class TestGenerateM3u8:
    def test_generate(self, tmp_path: Path) -> None:
        m4s = tmp_path / "video.m4s"
        m3u8 = tmp_path / "video.m3u8"
        _generate_m3u8(m4s, m3u8)
        content = m3u8.read_text()
        assert "#EXTM3U" in content
        assert "video.m4s" in content
        assert "#EXT-X-ENDLIST" in content


# ── metadata.py tests ─────────────────────────────────────────────────────────


class TestInjectMetadata:
    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake")
        meta = MediaMetadata(title="Test")

        with patch("birec.postprocess.metadata.find_ffmpeg", return_value=None):
            result = await inject_metadata(source, meta)
        assert result is False

    @pytest.mark.asyncio
    async def test_source_not_found(self, tmp_path: Path) -> None:
        source = tmp_path / "nonexistent.mp4"
        meta = MediaMetadata(title="Test")

        with patch(_META_FIND, return_value=_FFMPEG):
            result = await inject_metadata(source, meta)
        assert result is False

    @pytest.mark.asyncio
    async def test_success_in_place(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake mp4")
        meta = MediaMetadata(title="Test Title", artist="Test Artist")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_META_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await inject_metadata(source, meta)
        assert result is True

    @pytest.mark.asyncio
    async def test_success_with_output(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake mp4")
        output = tmp_path / "output.mp4"
        meta = MediaMetadata(title="Test")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_META_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await inject_metadata(source, meta, output=output)
        assert result is True

    @pytest.mark.asyncio
    async def test_ffmpeg_failure(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake mp4")
        meta = MediaMetadata(title="Test")

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with (
            patch(_META_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await inject_metadata(source, meta)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake mp4")
        meta = MediaMetadata(title="Test")

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with (
            patch(_META_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await inject_metadata(source, meta, timeout=0.001)
        assert result is False

    @pytest.mark.asyncio
    async def test_all_metadata_fields(self, tmp_path: Path) -> None:
        source = tmp_path / "test.mp4"
        source.write_bytes(b"fake mp4")
        meta = MediaMetadata(
            title="Title",
            artist="Artist",
            date="2026-01-01",
            description="Desc",
            comment="Comment",
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_META_FIND, return_value=_FFMPEG),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ) as mock_exec,
        ):
            result = await inject_metadata(source, meta)
        assert result is True
        # Verify all metadata args present
        call_args = str(mock_exec.call_args)
        assert "title=Title" in call_args
        assert "artist=Artist" in call_args


# ── danmaku_to_ass.py tests ──────────────────────────────────────────────────


class TestFindDmconvert:
    def test_find_dmconvert_exists(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/dmconvert"):
            assert find_dmconvert() == "/usr/bin/dmconvert"

    def test_find_dmconvert_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            assert find_dmconvert() is None


class TestConvertDanmakuToAss:
    @pytest.mark.asyncio
    async def test_dmconvert_not_found(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i></i>")
        output = tmp_path / "danmaku.ass"

        with patch(_DM_FIND, return_value=None):
            result = await convert_danmaku_to_ass(xml, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_xml_not_found(self, tmp_path: Path) -> None:
        xml = tmp_path / "nonexistent.xml"
        output = tmp_path / "danmaku.ass"

        with patch(
            "birec.postprocess.danmaku_to_ass.find_dmconvert",
            return_value="/usr/bin/dmconvert",
        ):
            result = await convert_danmaku_to_ass(xml, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_success(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i></i>")
        output = tmp_path / "danmaku.ass"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_DM_FIND, return_value="/usr/bin/dmconvert"),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await convert_danmaku_to_ass(xml, output)
        assert result is True

    @pytest.mark.asyncio
    async def test_with_custom_config(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i></i>")
        output = tmp_path / "danmaku.ass"
        config = DanmakuToAssConfig(font_size=30, resolution_x=1280)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(_DM_FIND, return_value="/usr/bin/dmconvert"),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ) as mock_exec,
        ):
            result = await convert_danmaku_to_ass(xml, output, config=config)
        assert result is True
        call_args = str(mock_exec.call_args)
        assert "30" in call_args  # font_size
        assert "1280x1080" in call_args  # resolution

    @pytest.mark.asyncio
    async def test_dmconvert_failure(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i></i>")
        output = tmp_path / "danmaku.ass"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with (
            patch(_DM_FIND, return_value="/usr/bin/dmconvert"),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await convert_danmaku_to_ass(xml, output)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i></i>")
        output = tmp_path / "danmaku.ass"

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with (
            patch(_DM_FIND, return_value="/usr/bin/dmconvert"),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            result = await convert_danmaku_to_ass(xml, output, timeout=0.001)
        assert result is False


# ── postprocessor.py extended tests ──────────────────────────────────────────


class TestPostprocessorExtended:
    @pytest.mark.asyncio
    async def test_process_m4s_remux(self, tmp_path: Path) -> None:
        """Test fMP4 (.m4s) remux path."""
        source = tmp_path / "test.m4s"
        source.write_bytes(b"fake m4s")
        output = tmp_path / "test.mp4"

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            on_completed=completed.append,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_fmp4_to_mp4",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await pp.start()
            pp.submit(source, output)
            await asyncio.sleep(0.2)
            await pp.stop()

        assert len(completed) == 1
        assert completed[0].status == PostprocessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_unknown_format(self, tmp_path: Path) -> None:
        """Test unknown format skips remux."""
        source = tmp_path / "test.xyz"
        source.write_bytes(b"fake data")
        output = tmp_path / "test.mp4"

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            on_completed=completed.append,
        )

        await pp.start()
        pp.submit(source, output)
        await asyncio.sleep(0.2)
        await pp.stop()

        assert len(completed) == 1
        assert completed[0].status == PostprocessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_danmaku_to_ass_conversion(self, tmp_path: Path) -> None:
        """Test danmaku XML→ASS conversion in pipeline."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"
        xml_file = tmp_path / "danmaku.xml"
        xml_file.write_text("<i></i>")

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=True,
            on_completed=completed.append,
        )

        with (
            patch(
                "birec.postprocess.postprocessor.remux_flv_to_mp4",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "birec.postprocess.postprocessor.convert_danmaku_to_ass",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_convert,
        ):
            await pp.start()
            pp.submit(source, output, related_files=[xml_file])
            await asyncio.sleep(0.2)
            await pp.stop()

        assert len(completed) == 1
        mock_convert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_related_files(self, tmp_path: Path) -> None:
        """Test AUTO delete removes related intermediate files."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"
        m3u8_file = tmp_path / "test.m3u8"
        m3u8_file.write_text("#EXTM3U")

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
            pp.submit(source, output, related_files=[m3u8_file])
            await asyncio.sleep(0.2)
            await pp.stop()

        assert not source.exists()
        assert not m3u8_file.exists()

    @pytest.mark.asyncio
    async def test_exception_in_processing(self, tmp_path: Path) -> None:
        """Test exception handling in worker."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            on_completed=completed.append,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ):
            await pp.start()
            pp.submit(source, output)
            await asyncio.sleep(0.2)
            await pp.stop()

        assert len(completed) == 1
        assert completed[0].status == PostprocessingStatus.FAILED
        assert "Unexpected error" in completed[0].error

    @pytest.mark.asyncio
    async def test_start_twice_noop(self) -> None:
        """Test starting twice is a no-op."""
        pp = Postprocessor()
        await pp.start()
        await pp.start()  # Should not create another task
        assert pp.is_running
        await pp.stop()

    @pytest.mark.asyncio
    async def test_delete_source_os_error(self, tmp_path: Path) -> None:
        """Test OSError during source deletion is handled gracefully."""
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "test.mp4"

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
        )

        with (
            patch(
                "birec.postprocess.postprocessor.remux_flv_to_mp4",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(Path, "unlink", side_effect=OSError("Permission denied")),
        ):
            await pp.start()
            pp.submit(source, output)
            await asyncio.sleep(0.2)
            await pp.stop()

        # Should complete despite delete failure
        assert pp.current_item is None
