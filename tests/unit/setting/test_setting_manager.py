import os

from birec.setting.env import EnvSettings
from birec.setting.models import Settings, TaskSettings
from birec.setting.setting_manager import SettingsManager


def test_load_missing_file_returns_defaults(tmp_path) -> None:
    path = str(tmp_path / "nope.toml")
    manager = SettingsManager.load(path)
    assert manager.settings.version == "1.0"
    assert manager.settings.tasks == []


def test_dump_then_load_roundtrip(tmp_path) -> None:
    path = str(tmp_path / "settings.toml")
    settings = Settings(tasks=[TaskSettings(room_id=42)])
    settings.recorder.quality_number = 20000
    manager = SettingsManager(settings, path)
    manager.dump()

    reloaded = SettingsManager.load(path)
    assert reloaded.settings.recorder.quality_number == 20000
    assert reloaded.settings.tasks[0].room_id == 42


def test_dump_writes_camel_case_and_excludes_none(tmp_path) -> None:
    path = str(tmp_path / "settings.toml")
    settings = Settings(tasks=[TaskSettings(room_id=7)])
    SettingsManager(settings, path).dump()

    content = (tmp_path / "settings.toml").read_text()
    assert "baseApiUrls" in content
    assert "base_api_urls" not in content
    # task option None fields must not be serialized
    assert "= null" not in content


def test_load_accepts_camel_case_keys(tmp_path) -> None:
    path = tmp_path / "s.toml"
    path.write_text(
        '[recorder]\nstreamFormat = "fmp4"\nqualityNumber = 400\n',
        encoding="utf8",
    )
    manager = SettingsManager.load(str(path))
    assert manager.settings.recorder.stream_format == "fmp4"
    assert manager.settings.recorder.quality_number == 400


def test_env_overlay_out_and_log_dir() -> None:
    settings = Settings()
    manager = SettingsManager(settings, "unused.toml")
    manager.apply_env_settings(
        EnvSettings.model_construct(out_dir="/data/out", log_dir="/data/log")
    )
    assert manager.settings.output.out_dir == "/data/out"
    assert manager.settings.logging.log_dir == "/data/log"


def test_env_settings_reads_birec_prefix(monkeypatch) -> None:
    monkeypatch.setenv("BIREC_OUT_DIR", "/env/out")
    monkeypatch.setenv("BIREC_CONFIG", "/env/settings.toml")
    env = EnvSettings()
    assert env.out_dir == "/env/out"
    assert env.config == "/env/settings.toml"


def test_load_with_env_expands_user(tmp_path, monkeypatch) -> None:
    path = tmp_path / "conf.toml"
    path.write_text('version = "1.0"\n', encoding="utf8")
    monkeypatch.setenv("BIREC_CONFIG", str(path))
    monkeypatch.setenv("BIREC_OUT_DIR", str(tmp_path / "out"))
    manager = SettingsManager.load_with_env()
    assert manager.settings.output.out_dir == str(tmp_path / "out")
    assert os.path.isabs(manager.path)


def test_find_task_settings() -> None:
    settings = Settings(tasks=[TaskSettings(room_id=1), TaskSettings(room_id=2)])
    manager = SettingsManager(settings, "x.toml")
    assert manager.find_task_settings(2) is not None
    assert manager.find_task_settings(99) is None
    assert manager.has_task_settings(1) is True
