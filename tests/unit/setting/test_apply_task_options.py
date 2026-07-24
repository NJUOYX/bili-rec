import pytest

from birec.setting.helpers import shadow_settings, update_settings
from birec.setting.models import (
    DanmakuOptions,
    DanmakuSettings,
    RecorderOptions,
    RecorderSettings,
    Settings,
    TaskSettings,
)
from birec.setting.setting_manager import SettingsManager


def _manager_with_task(task: TaskSettings, **global_overrides) -> SettingsManager:
    settings = Settings(tasks=[task])
    for section, values in global_overrides.items():
        target = getattr(settings, section)
        for key, value in values.items():
            setattr(target, key, value)
    return SettingsManager(settings, "x.toml")


def test_resolve_task_falls_back_to_global_when_none() -> None:
    task = TaskSettings(room_id=1)  # all option fields None
    manager = _manager_with_task(task, recorder={"quality_number": 20000})
    resolved = manager.resolve_task_settings(1)
    assert resolved["recorder"].quality_number == 20000


def test_resolve_task_overrides_when_set() -> None:
    task = TaskSettings(room_id=1, recorder=RecorderOptions(quality_number=400))
    manager = _manager_with_task(task, recorder={"quality_number": 20000})
    resolved = manager.resolve_task_settings(1)
    assert resolved["recorder"].quality_number == 400
    # unset fields still fall back to global defaults
    assert resolved["recorder"].stream_format == "flv"


def test_resolve_task_partial_override_keeps_other_fields() -> None:
    task = TaskSettings(room_id=1, danmaku=DanmakuOptions(danmu_uname=True))
    manager = _manager_with_task(task)
    resolved = manager.resolve_task_settings(1)
    assert resolved["danmaku"].danmu_uname is True
    assert resolved["danmaku"].record_gift_send is True  # global default


def test_resolve_task_does_not_mutate_global() -> None:
    task = TaskSettings(room_id=1, recorder=RecorderOptions(quality_number=80))
    manager = _manager_with_task(task, recorder={"quality_number": 20000})
    manager.resolve_task_settings(1)
    assert manager.settings.recorder.quality_number == 20000


def test_resolve_task_missing_room_raises() -> None:
    manager = SettingsManager(Settings(), "x.toml")
    with pytest.raises(ValueError):
        manager.resolve_task_settings(999)


def test_shadow_settings_skips_none() -> None:
    src = RecorderOptions(quality_number=400)  # only this set, rest None
    dst = RecorderSettings()
    shadow_settings(src, dst)
    assert dst.quality_number == 400
    assert dst.stream_format == "flv"  # untouched by None src field


def test_update_settings_copies_only_set_fields() -> None:
    src = DanmakuSettings.model_construct(danmu_uname=True)
    dst = DanmakuSettings()
    update_settings(src, dst)
    assert dst.danmu_uname is True
