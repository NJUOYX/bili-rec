"""Extended tests for postprocess module to achieve ≥85% coverage."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.postprocess.danmaku_to_ass import (
    DanmakuToAssConfig,
    convert_danmaku_to_ass,
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
_SUBPROCESS = "asyncio.create_subprocess_exec"

# One rolling danmaku, enough for the converter to emit a dialogue line.
_DANMAKU_XML = (
    "<?xml version='1.0' encoding='utf-8'?>\n"
    "<i>"
    '<d p="1.000,1,25,16777215,1733047466414,0,73c9f86f,-1189105972" '
    'uid="0" user="X***">hello</d>'
    "</i>"
)

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


class TestConvertDanmakuToAss:
    @pytest.mark.asyncio
    async def test_xml_not_found(self, tmp_path: Path) -> None:
        xml = tmp_path / "nonexistent.xml"
        output = tmp_path / "danmaku.ass"

        assert await convert_danmaku_to_ass(xml, output) is False

    @pytest.mark.asyncio
    async def test_writes_a_real_ass_file(self, tmp_path: Path) -> None:
        """Regression: the conversion must actually produce the ASS file.

        It used to shell out to a ``dmconvert`` binary with flags its CLI does
        not accept, so the step silently failed even with the option enabled.
        """
        xml = tmp_path / "danmaku.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        output = tmp_path / "danmaku.ass"

        assert await convert_danmaku_to_ass(xml, output) is True
        content = output.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "hello" in content

    @pytest.mark.asyncio
    async def test_config_reaches_the_output(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        output = tmp_path / "danmaku.ass"
        config = DanmakuToAssConfig(font_size=30, resolution_x=1280, resolution_y=720)

        assert await convert_danmaku_to_ass(xml, output, config=config) is True
        content = output.read_text(encoding="utf-8")
        assert "PlayResX: 1280" in content
        assert "PlayResY: 720" in content

    @pytest.mark.asyncio
    async def test_creates_missing_output_directory(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        output = tmp_path / "subs" / "danmaku.ass"

        assert await convert_danmaku_to_ass(xml, output) is True
        assert output.exists()

    @pytest.mark.asyncio
    async def test_malformed_xml_fails_without_raising(self, tmp_path: Path) -> None:
        """A broken XML must not take the whole post-processing item down."""
        xml = tmp_path / "danmaku.xml"
        xml.write_text("<i><d p=", encoding="utf-8")
        output = tmp_path / "danmaku.ass"

        assert await convert_danmaku_to_ass(xml, output) is False

    @pytest.mark.asyncio
    async def test_missing_dmconvert_is_reported_not_raised(
        self, tmp_path: Path
    ) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        output = tmp_path / "danmaku.ass"

        with patch.dict(sys.modules, {"dmconvert": None}):
            assert await convert_danmaku_to_ass(xml, output) is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path) -> None:
        xml = tmp_path / "danmaku.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        output = tmp_path / "danmaku.ass"

        async def _never(*_args: object, **_kwargs: object) -> None:
            await asyncio.sleep(10)

        with patch("asyncio.to_thread", new=_never):
            result = await convert_danmaku_to_ass(xml, output, timeout=0.01)
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

        async def _remux(_src: Path, dst: Path) -> bool:
            # A remux that reports success but leaves no file behind is not a
            # remux; the deletion downstream is only safe because this exists.
            dst.write_bytes(b"fake mp4")
            return True

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new=_remux,
        ):
            await pp.start()
            pp.submit(source, output, related_files=[m3u8_file])
            await asyncio.sleep(0.2)
            await pp.stop()

        assert output.exists()
        assert not source.exists()
        assert not m3u8_file.exists()

    @pytest.mark.asyncio
    async def test_source_survives_when_the_remux_is_off(self, tmp_path: Path) -> None:
        """Regression: turning the remux off must not delete the recording.

        Deleting the source was the last step regardless, and the remux was the
        only step that would have produced a replacement. So switching it off —
        an ordinary choice for someone who wants the original file — silently
        destroyed every recording once it finished.
        """
        source = tmp_path / "test.flv"
        source.write_bytes(b"fake flv")

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=False)
        await pp.start()
        pp.submit(source, tmp_path / "test.mp4")
        await asyncio.sleep(0.2)
        await pp.stop()

        assert source.exists(), "the recording was deleted with nothing to replace it"
        assert not (tmp_path / "test.mp4").exists()

    @pytest.mark.asyncio
    async def test_an_unknown_format_is_not_deleted(self, tmp_path: Path) -> None:
        """Regression: a format we cannot remux must not be deleted either.

        The unknown-format branch points the output back at the source and calls
        it a success, so the delete step then removed the very file it had just
        declared to be the output.
        """
        source = tmp_path / "test.m3u8"
        source.write_text("#EXTM3U")

        pp = Postprocessor(remux_enabled=True, inject_metadata_enabled=False)
        await pp.start()
        pp.submit(source, tmp_path / "test.mp4")
        await asyncio.sleep(0.2)
        await pp.stop()

        assert source.exists(), "the output was deleted for being its own source"

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


class TestPostprocessorDanmakuConversion:
    """The danmaku step must survive a broken remux and honour hot updates."""

    async def _run(
        self,
        pp: Postprocessor,
        source: Path,
        output: Path,
        related_files: list[Path] | None = None,
    ) -> None:
        await pp.start()
        pp.submit(source, output, related_files=related_files)
        await asyncio.sleep(0.2)
        await pp.stop()

    @pytest.mark.asyncio
    async def test_ass_is_written_for_related_xml(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        xml = tmp_path / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=False,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=True,
        )
        await self._run(pp, source, tmp_path / "rec.mp4", [xml])

        assert (tmp_path / "rec.ass").exists()

    @pytest.mark.asyncio
    async def test_ass_survives_a_failing_remux(self, tmp_path: Path) -> None:
        """Regression: a failed remux used to abort the whole pipeline.

        The danmaku conversion ran after it, so a missing or unhappy ffmpeg cost
        the user their subtitles too even though the two are unrelated.
        """
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        xml = tmp_path / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=True,
            on_completed=completed.append,
        )

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await self._run(pp, source, tmp_path / "rec.mp4", [xml])

        assert completed[0].status == PostprocessingStatus.FAILED
        assert (tmp_path / "rec.ass").exists()

    @pytest.mark.asyncio
    async def test_related_danmaku_files_are_kept(self, tmp_path: Path) -> None:
        """The XML/JSONL the ASS came from must outlive the auto-cleanup."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        xml = tmp_path / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")
        raw = tmp_path / "rec.jsonl"
        raw.write_text("{}\n", encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=False,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=True,
        )
        await self._run(pp, source, tmp_path / "rec.mp4", [xml, raw])

        assert xml.exists()
        assert raw.exists()

    @pytest.mark.asyncio
    async def test_ass_lands_beside_video_when_xml_is_tiered_in_meta(
        self, tmp_path: Path
    ) -> None:
        """#37: the XML moved into a meta/ subdirectory, but players only
        auto-load subtitles from the video's own directory, so the ASS must
        be written beside the video rather than next to the XML."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        xml = meta_dir / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=False,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=True,
        )
        await self._run(pp, source, tmp_path / "rec.mp4", [xml])

        assert (tmp_path / "rec.ass").exists()
        assert not (meta_dir / "rec.ass").exists()

    @pytest.mark.asyncio
    async def test_ffmpeg_meta_file_is_auto_deleted_after_remux(
        self, tmp_path: Path
    ) -> None:
        """#37: the .meta intermediate file sits beside the video and is handed
        over as a related file so the existing AUTO delete cleans it up."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        meta_file = tmp_path / "rec.meta"
        meta_file.write_text("title=x", encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
        )

        async def _remux(_src: Path, dst: Path) -> bool:
            dst.write_bytes(b"fake mp4")
            return True

        with patch("birec.postprocess.postprocessor.remux_flv_to_mp4", new=_remux):
            await self._run(pp, source, tmp_path / "rec.mp4", [meta_file])

        assert (tmp_path / "rec.mp4").exists()
        assert not source.exists()
        assert not meta_file.exists()

    @pytest.mark.asyncio
    async def test_tiered_meta_json_is_auto_deleted_after_remux(
        self, tmp_path: Path
    ) -> None:
        """A .meta.json tiered into meta/ is an intermediate file too."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        meta_json = meta_dir / "rec.meta.json"
        meta_json.write_text("{}", encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=False,
        )

        async def _remux(_src: Path, dst: Path) -> bool:
            dst.write_bytes(b"fake mp4")
            return True

        with patch("birec.postprocess.postprocessor.remux_flv_to_mp4", new=_remux):
            await self._run(pp, source, tmp_path / "rec.mp4", [meta_json])

        assert not meta_json.exists()

    @pytest.mark.asyncio
    async def test_disabled_conversion_writes_nothing(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        xml = tmp_path / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=False,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=False,
        )
        await self._run(pp, source, tmp_path / "rec.mp4", [xml])

        assert not (tmp_path / "rec.ass").exists()

    @pytest.mark.asyncio
    async def test_update_options_reaches_the_running_worker(
        self, tmp_path: Path
    ) -> None:
        """Regression: a settings change must apply to an already running task.

        The switches were frozen at construction, so enabling danmaku→ASS only
        took effect for rooms added afterwards.
        """
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        xml = tmp_path / "rec.xml"
        xml.write_text(_DANMAKU_XML, encoding="utf-8")

        pp = Postprocessor(
            remux_enabled=False,
            inject_metadata_enabled=False,
            danmaku_to_ass_enabled=False,
        )
        pp.update_options(danmaku_to_ass_enabled=True)
        assert pp.danmaku_to_ass_enabled is True

        await self._run(pp, source, tmp_path / "rec.mp4", [xml])

        assert (tmp_path / "rec.ass").exists()

    def test_update_options_leaves_omitted_switches_alone(self) -> None:
        config = DanmakuToAssConfig(font_size=30)
        pp = Postprocessor(
            remux_enabled=True,
            inject_metadata_enabled=True,
            danmaku_to_ass_enabled=True,
            danmaku_config=config,
        )

        pp.update_options(remux_enabled=False)

        assert pp.remux_enabled is False
        assert pp.inject_metadata_enabled is True
        assert pp.danmaku_to_ass_enabled is True
        assert pp.danmaku_config is config

    def test_update_options_replaces_the_danmaku_config(self) -> None:
        pp = Postprocessor()
        config = DanmakuToAssConfig(font_size=48, resolution_x=1280)

        pp.update_options(danmaku_config=config)

        assert pp.danmaku_config == config

    @pytest.mark.asyncio
    async def test_completion_listener_can_be_set_late(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")

        completed: list[PostprocessingItem] = []
        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=False)
        pp.set_completion_listener(completed.append)

        await self._run(pp, source, tmp_path / "rec.mp4")

        assert [item.status for item in completed] == [PostprocessingStatus.COMPLETED]


class TestPostprocessorInjectMetadataWiring:
    """Regression: the INJECTING step must actually call inject_metadata (#30).

    Previously the postprocessor set the status to INJECTING and immediately
    moved on without invoking inject_metadata, so enabling the feature had no
    observable effect on the output file.
    """

    _INJECT = "birec.postprocess.postprocessor.inject_metadata"

    async def _run(
        self,
        pp: Postprocessor,
        source: Path,
        output: Path,
        metadata: MediaMetadata | None = None,
    ) -> list[PostprocessingItem]:
        completed: list[PostprocessingItem] = []
        pp.set_completion_listener(completed.append)
        await pp.start()
        pp.submit(source, output, metadata=metadata)
        await asyncio.sleep(0.2)
        await pp.stop()
        return completed

    @pytest.mark.asyncio
    async def test_enabled_with_metadata_calls_inject(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"
        meta = MediaMetadata(title="Test Stream", artist="Streamer")

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=True)

        with patch(self._INJECT, new_callable=AsyncMock, return_value=True) as m:
            completed = await self._run(pp, source, output, metadata=meta)

        assert completed[0].status == PostprocessingStatus.COMPLETED
        m.assert_awaited_once()
        args = m.call_args[0]
        assert args[0] == source  # output doesn't exist → falls back to source
        assert args[1] is meta

    @pytest.mark.asyncio
    async def test_disabled_with_metadata_skips_inject(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"
        meta = MediaMetadata(title="Test")

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=False)

        with patch(self._INJECT, new_callable=AsyncMock) as m:
            completed = await self._run(pp, source, output, metadata=meta)

        assert completed[0].status == PostprocessingStatus.COMPLETED
        m.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enabled_without_metadata_skips_inject(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=True)

        with patch(self._INJECT, new_callable=AsyncMock) as m:
            completed = await self._run(pp, source, output, metadata=None)

        assert completed[0].status == PostprocessingStatus.COMPLETED
        m.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inject_failure_does_not_fail_item(self, tmp_path: Path) -> None:
        """Metadata injection failure must be non-fatal (item still completes)."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"
        meta = MediaMetadata(title="Test")

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=True)

        with patch(self._INJECT, new_callable=AsyncMock, return_value=False):
            completed = await self._run(pp, source, output, metadata=meta)

        assert completed[0].status == PostprocessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_inject_targets_remuxed_output(self, tmp_path: Path) -> None:
        """When the remux produced an output file, inject into that, not the source."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"
        meta = MediaMetadata(title="Test")

        pp = Postprocessor(remux_enabled=True, inject_metadata_enabled=True)

        async def _fake_remux(src: Path, dst: Path) -> bool:
            dst.write_bytes(b"fake mp4")
            return True

        with (
            patch(
                "birec.postprocess.postprocessor.remux_flv_to_mp4",
                new=_fake_remux,
            ),
            patch(self._INJECT, new_callable=AsyncMock, return_value=True) as m,
        ):
            completed = await self._run(pp, source, output, metadata=meta)

        assert completed[0].status == PostprocessingStatus.COMPLETED
        m.assert_awaited_once()
        assert m.call_args[0][0] == output  # inject targets the remuxed file

    @pytest.mark.asyncio
    async def test_inject_exception_isolated(self, tmp_path: Path) -> None:
        """An exception from inject_metadata must not crash the pipeline."""
        source = tmp_path / "rec.flv"
        source.write_bytes(b"fake flv")
        output = tmp_path / "rec.mp4"
        meta = MediaMetadata(title="Test")

        pp = Postprocessor(remux_enabled=False, inject_metadata_enabled=True)

        with patch(
            self._INJECT,
            new_callable=AsyncMock,
            side_effect=RuntimeError("ffmpeg exploded"),
        ):
            completed = await self._run(pp, source, output, metadata=meta)

        # The worker catches the exception and marks the item FAILED
        assert len(completed) == 1
        assert completed[0].status == PostprocessingStatus.FAILED
