"""Tests for the session-directory sidecar layout (#37).

One broadcast produces one session directory; danmaku and metadata sidecars
(.xml/.jsonl/covers/.meta.json) live in a ``meta/`` subdirectory under the
video, while subtitles (.ass) and the ffmpeg intermediate file (.meta) stay
beside the video so players can pick the subtitles up automatically.
"""

from __future__ import annotations

from pathlib import Path

from birec.path import (
    META_SUBDIR_EXTENSIONS,
    META_SUBDIR_NAME,
    SIDECAR_EXTENSIONS,
    derive_path,
)


class TestDerivePathLayout:
    def test_danmaku_xml_lands_in_meta_subdir(self) -> None:
        base = Path("/recordings/123 - streamer/session/blive_123.flv")
        result = derive_path(base, ".xml")
        assert result == Path("/recordings/123 - streamer/session/meta/blive_123.xml")

    def test_raw_danmaku_jsonl_lands_in_meta_subdir(self) -> None:
        base = Path("/recordings/session/blive_123.flv")
        assert derive_path(base, ".jsonl") == Path(
            "/recordings/session/meta/blive_123.jsonl"
        )

    def test_cover_images_land_in_meta_subdir(self) -> None:
        base = Path("/recordings/session/blive_123.flv")
        assert derive_path(base, ".jpg") == Path(
            "/recordings/session/meta/blive_123.jpg"
        )
        assert derive_path(base, ".png") == Path(
            "/recordings/session/meta/blive_123.png"
        )

    def test_meta_json_lands_in_meta_subdir(self) -> None:
        base = Path("/recordings/session/blive_123.flv")
        result = derive_path(base, ".meta.json")
        assert result == Path("/recordings/session/meta/blive_123.meta.json")

    def test_ass_stays_beside_the_video(self) -> None:
        """Players auto-load subtitles only from the video's own directory."""
        base = Path("/recordings/session/blive_123.flv")
        assert derive_path(base, ".ass") == Path("/recordings/session/blive_123.ass")

    def test_ffmpeg_meta_stays_beside_the_video(self) -> None:
        """The .meta intermediate file is auto-deleted beside the video."""
        base = Path("/recordings/session/blive_123.flv")
        assert derive_path(base, ".meta") == Path("/recordings/session/blive_123.meta")

    def test_unknown_extension_stays_beside_the_video(self) -> None:
        base = Path("/recordings/session/blive_123.flv")
        assert derive_path(base, ".webp") == Path("/recordings/session/blive_123.webp")

    def test_deduped_video_stem_is_kept(self) -> None:
        """A deduped video (blive_123_1.flv) keeps its suffix in sidecars."""
        base = Path("/recordings/session/blive_123_1.flv")
        assert derive_path(base, ".xml") == Path(
            "/recordings/session/meta/blive_123_1.xml"
        )

    def test_meta_subdir_extensions_are_sidecars(self) -> None:
        """Everything tiered into meta/ is still a sidecar extension."""
        assert META_SUBDIR_EXTENSIONS <= SIDECAR_EXTENSIONS

    def test_ass_and_meta_are_not_tiered(self) -> None:
        assert ".ass" not in META_SUBDIR_EXTENSIONS
        assert ".meta" not in META_SUBDIR_EXTENSIONS

    def test_meta_subdir_name(self) -> None:
        assert META_SUBDIR_NAME == "meta"
