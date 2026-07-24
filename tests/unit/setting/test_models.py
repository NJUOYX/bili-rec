import pytest
from pydantic import ValidationError

from birec.setting.models import (
    BiliApiSettings,
    DanmakuSettings,
    HeaderSettings,
    OutputSettings,
    PostprocessingSettings,
    RecorderSettings,
    Settings,
    SpaceSettings,
    TaskSettings,
)


def test_defaults_match_design() -> None:
    s = Settings()
    assert s.version == "1.0"
    assert s.tasks == []
    assert s.recorder.stream_format == "flv"
    assert s.recorder.quality_number == 10000
    assert s.recorder.save_cover is True
    assert s.recorder.cover_save_strategy == "dedup"
    assert s.postprocessing.remux_to_mp4 is True
    assert s.postprocessing.inject_extra_metadata is True
    assert s.danmaku.record_toast is True
    assert s.space.space_threshold == 1024**3
    assert s.bili_api.base_api_urls == ["https://api.bilibili.com"]


def test_camel_case_alias_roundtrip() -> None:
    data = {
        "baseApiUrls": ["https://x"],
        "baseLiveApiUrls": ["https://y"],
        "basePlayInfoApiUrls": ["https://z"],
    }
    model = BiliApiSettings.model_validate(data)
    assert model.base_api_urls == ["https://x"]
    dumped = model.model_dump(by_alias=True)
    assert dumped["baseApiUrls"] == ["https://x"]
    assert "base_api_urls" not in dumped


def test_populate_by_name_accepts_snake_case() -> None:
    model = RecorderSettings.model_validate({"stream_format": "fmp4"})
    assert model.stream_format == "fmp4"


def test_recorder_timeout_validation() -> None:
    RecorderSettings(read_timeout=3)
    with pytest.raises(ValidationError):
        RecorderSettings(read_timeout=4)
    with pytest.raises(ValidationError):
        RecorderSettings(fmp4_stream_timeout=7)
    with pytest.raises(ValidationError):
        RecorderSettings(disconnection_timeout=100)


def test_recorder_buffer_size_bounds() -> None:
    RecorderSettings(buffer_size=4096)
    with pytest.raises(ValidationError):
        RecorderSettings(buffer_size=1024)  # below minimum
    with pytest.raises(ValidationError):
        RecorderSettings(buffer_size=4097)  # not multiple of 2


def test_space_allowed_values() -> None:
    SpaceSettings(check_interval=60, space_threshold=1024**3)
    with pytest.raises(ValidationError):
        SpaceSettings(check_interval=45)
    with pytest.raises(ValidationError):
        SpaceSettings(space_threshold=2 * 1024**3)


def test_postprocessing_ass_ranges() -> None:
    PostprocessingSettings(ass_font_size=38, ass_resolution_x=1920)
    with pytest.raises(ValidationError):
        PostprocessingSettings(ass_font_size=0)
    with pytest.raises(ValidationError):
        PostprocessingSettings(ass_resolution_x=99999)


def test_output_path_template_validation() -> None:
    OutputSettings(path_template="{roomid} - {uname}/rec_{year}{month}{day}")
    with pytest.raises(ValidationError):
        OutputSettings(path_template="no-placeholder-here")


def test_task_room_id_required_and_positive() -> None:
    task = TaskSettings(room_id=123)
    assert task.enable_monitor is True
    assert task.enable_recorder is True
    with pytest.raises(ValidationError):
        TaskSettings(room_id=0)


def test_tasks_max_limit() -> None:
    tasks = [TaskSettings(room_id=i) for i in range(1, 5)]
    Settings(tasks=tasks)
    too_many = [TaskSettings(room_id=i) for i in range(1, 102)]
    with pytest.raises(ValidationError):
        Settings(tasks=too_many)


def test_header_default_user_agent() -> None:
    h = HeaderSettings()
    assert "Mozilla/5.0" in h.user_agent
    assert h.cookie == ""


def test_danmaku_defaults() -> None:
    d = DanmakuSettings()
    assert d.danmu_uname is False
    assert d.record_gift_send is True
    assert d.save_raw_danmaku is False
