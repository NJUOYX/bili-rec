"""Pydantic v2 configuration schema for birec.

External representation uses camelCase aliases; internal fields are snake_case.
Notification/webhook/api_key/filesize/duration/delete_source are intentionally
dropped relative to blrec.
"""

from __future__ import annotations

import os
import re
from typing import Annotated, ClassVar, Final

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field, field_validator

from birec.bili.typing import QualityNumber, StreamFormat
from birec.logging.typing import LOG_LEVEL
from birec.path import PATH_TEMPLATE_PRESETS
from birec.setting.typing import CoverSaveStrategy, RecordingMode
from birec.utils.string import camel_case

__all__ = (
    "DEFAULT_OUT_DIR",
    "DEFAULT_LOG_DIR",
    "DEFAULT_SETTINGS_FILE",
    "BiliApiSettings",
    "HeaderOptions",
    "HeaderSettings",
    "DanmakuOptions",
    "DanmakuSettings",
    "RecorderOptions",
    "RecorderSettings",
    "OutputOptions",
    "OutputSettings",
    "PostprocessingOptions",
    "PostprocessingSettings",
    "LoggingSettings",
    "SpaceSettings",
    "TaskOptions",
    "TaskSettings",
    "Settings",
    "SettingsIn",
    "SettingsOut",
)


DEFAULT_OUT_DIR: Final[str] = os.environ.get("BIREC_DEFAULT_OUT_DIR", ".")
DEFAULT_LOG_DIR: Final[str] = os.environ.get("BIREC_DEFAULT_LOG_DIR", "~/.birec/logs/")
DEFAULT_SETTINGS_FILE: Final[str] = os.environ.get(
    "BIREC_DEFAULT_SETTINGS_FILE", "~/.birec/settings.toml"
)

_PATH_TEMPLATE_PATTERN = r"""^
    (?:
        [^\\/:*?"<>|\t\n\r\f\v\{\}]*?
        \{
        (?:
            roomid|uname|title|area|parent_area|
            year|month|day|hour|minute|second
        )
        \}
        [^\\/:*?"<>|\t\n\r\f\v\{\}]*?
    )+?
    (?:
        /
        (?:
            [^\\/:*?"<>|\t\n\r\f\v\{\}]*?
            \{
            (?:
                roomid|uname|title|area|parent_area|
                year|month|day|hour|minute|second
            )
            \}
            [^\\/:*?"<>|\t\n\r\f\v\{\}]*?
        )+?
    )*
$"""


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        alias_generator=camel_case,
        populate_by_name=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class BiliApiSettings(BaseModel):
    base_api_urls: list[str] = ["https://api.bilibili.com"]
    base_live_api_urls: list[str] = ["https://api.live.bilibili.com"]
    base_play_info_api_urls: list[str] = ["https://api.live.bilibili.com"]


class HeaderOptions(BaseModel):
    user_agent: str | None = None
    cookie: str | None = None


class HeaderSettings(HeaderOptions):
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    cookie: str = ""


class DanmakuOptions(BaseModel):
    danmu_uname: bool | None = None
    record_gift_send: bool | None = None
    record_free_gifts: bool | None = None
    record_guard_buy: bool | None = None
    record_super_chat: bool | None = None
    record_toast: bool | None = None
    save_raw_danmaku: bool | None = None


class DanmakuSettings(DanmakuOptions):
    danmu_uname: bool = False
    record_gift_send: bool = True
    record_free_gifts: bool = True
    record_guard_buy: bool = True
    record_super_chat: bool = True
    record_toast: bool = True
    save_raw_danmaku: bool = False


_TIMEOUT_VALUES = frozenset((3, 5, 10, 30, 60, 180, 300, 600))
_DISCONNECTION_VALUES = frozenset(60 * i for i in (3, 5, 10, 15, 20, 30))


class RecorderOptions(BaseModel):
    stream_format: StreamFormat | None = None
    recording_mode: RecordingMode | None = None
    quality_number: QualityNumber | None = None
    fmp4_stream_timeout: int | None = None
    read_timeout: int | None = None
    disconnection_timeout: int | None = None
    buffer_size: (
        Annotated[int, Field(ge=4096, le=1024**2 * 512, multiple_of=2)] | None
    ) = None
    save_cover: bool | None = None
    cover_save_strategy: CoverSaveStrategy | None = None

    @field_validator("fmp4_stream_timeout", "read_timeout")
    @classmethod
    def _validate_timeout(cls, value: int | None) -> int | None:
        if value is not None and value not in _TIMEOUT_VALUES:
            raise ValueError(f"value must be one of {sorted(_TIMEOUT_VALUES)}")
        return value

    @field_validator("disconnection_timeout")
    @classmethod
    def _validate_disconnection(cls, value: int | None) -> int | None:
        if value is not None and value not in _DISCONNECTION_VALUES:
            raise ValueError(f"value must be one of {sorted(_DISCONNECTION_VALUES)}")
        return value


class RecorderSettings(RecorderOptions):
    stream_format: StreamFormat = "flv"
    recording_mode: RecordingMode = "standard"
    quality_number: QualityNumber = 10000
    fmp4_stream_timeout: int = 10
    read_timeout: int = 3
    disconnection_timeout: int = 600
    buffer_size: Annotated[int, Field(ge=4096, le=1024**2 * 512, multiple_of=2)] = 8192
    save_cover: bool = True
    cover_save_strategy: CoverSaveStrategy = "dedup"


class OutputOptions(BaseModel):
    path_template: str | None = None

    @field_validator("path_template")
    @classmethod
    def _validate_path_template(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(
            _PATH_TEMPLATE_PATTERN, value, re.VERBOSE
        ):
            raise ValueError(f"invalid path template: '{value}'")
        return value


class OutputSettings(OutputOptions):
    out_dir: str = DEFAULT_OUT_DIR
    # New deployments organize one broadcast into its own dated session
    # directory (#37); an existing config.toml keeps whatever it persists.
    path_template: str = PATH_TEMPLATE_PRESETS[0]


class PostprocessingOptions(BaseModel):
    remux_to_mp4: bool | None = None
    inject_extra_metadata: bool | None = None
    danmaku_to_ass: bool | None = None
    ass_font_size: Annotated[int, Field(ge=1, le=200)] | None = None
    ass_sc_font_size: Annotated[int, Field(ge=1, le=200)] | None = None
    ass_resolution_x: Annotated[int, Field(ge=1, le=7680)] | None = None
    ass_resolution_y: Annotated[int, Field(ge=1, le=4320)] | None = None


class PostprocessingSettings(PostprocessingOptions):
    remux_to_mp4: bool = True
    inject_extra_metadata: bool = True
    danmaku_to_ass: bool = False
    ass_font_size: Annotated[int, Field(ge=1, le=200)] = 38
    ass_sc_font_size: Annotated[int, Field(ge=1, le=200)] = 38
    ass_resolution_x: Annotated[int, Field(ge=1, le=7680)] = 1920
    ass_resolution_y: Annotated[int, Field(ge=1, le=4320)] = 1080


class LoggingSettings(BaseModel):
    log_dir: str = DEFAULT_LOG_DIR
    console_log_level: LOG_LEVEL = "INFO"
    backup_count: Annotated[int, Field(ge=0, le=90)] = 30


_CHECK_INTERVAL_VALUES = frozenset((0, 10, 30, *(60 * i for i in (1, 3, 5, 10))))
_SPACE_THRESHOLD_VALUES = frozenset(1024**3 * i for i in (1, 3, 5, 10, 20))


class SpaceSettings(BaseModel):
    check_interval: int = 60
    space_threshold: int = 1024**3
    recycle_records: bool = False

    @field_validator("check_interval")
    @classmethod
    def _validate_interval(cls, value: int) -> int:
        if value not in _CHECK_INTERVAL_VALUES:
            raise ValueError(f"value must be one of {sorted(_CHECK_INTERVAL_VALUES)}")
        return value

    @field_validator("space_threshold")
    @classmethod
    def _validate_threshold(cls, value: int) -> int:
        if value not in _SPACE_THRESHOLD_VALUES:
            raise ValueError(f"value must be one of {sorted(_SPACE_THRESHOLD_VALUES)}")
        return value


class TaskOptions(BaseModel):
    output: OutputOptions = OutputOptions()
    header: HeaderOptions = HeaderOptions()
    danmaku: DanmakuOptions = DanmakuOptions()
    recorder: RecorderOptions = RecorderOptions()
    postprocessing: PostprocessingOptions = PostprocessingOptions()


class TaskSettings(TaskOptions):
    room_id: Annotated[int, Field(ge=1, lt=2**100)]
    enable_monitor: bool = True
    enable_recorder: bool = True


class Settings(BaseModel):
    MAX_TASKS: ClassVar[int] = 100

    version: str = "1.0"
    tasks: Annotated[list[TaskSettings], Field(max_length=MAX_TASKS)] = []
    output: OutputSettings = OutputSettings()
    logging: LoggingSettings = LoggingSettings()
    bili_api: BiliApiSettings = BiliApiSettings()
    header: HeaderSettings = HeaderSettings()
    danmaku: DanmakuSettings = DanmakuSettings()
    recorder: RecorderSettings = RecorderSettings()
    postprocessing: PostprocessingSettings = PostprocessingSettings()
    space: SpaceSettings = SpaceSettings()


class SettingsIn(BaseModel):
    output: OutputSettings | None = None
    logging: LoggingSettings | None = None
    bili_api: BiliApiSettings | None = None
    header: HeaderSettings | None = None
    danmaku: DanmakuSettings | None = None
    recorder: RecorderSettings | None = None
    postprocessing: PostprocessingSettings | None = None
    space: SpaceSettings | None = None


class SettingsOut(SettingsIn):
    version: str | None = None
    tasks: list[TaskSettings] | None = None
