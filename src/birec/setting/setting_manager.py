"""TOML-backed settings manager with environment overlay."""

from __future__ import annotations

import os
import tomllib
from typing import Any

import tomli_w

from birec.setting.env import EnvSettings
from birec.setting.models import Settings, SettingsOut, TaskSettings

__all__ = ("SettingsManager",)


class SettingsManager:
    def __init__(self, settings: Settings, path: str) -> None:
        self._settings = settings
        self._path = path

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def path(self) -> str:
        return self._path

    @classmethod
    def load(cls, path: str) -> SettingsManager:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded):
            with open(expanded, "rb") as file:
                data: dict[str, Any] = tomllib.load(file)
            settings = Settings.model_validate(data)
        else:
            settings = Settings()
        return cls(settings, expanded)

    @classmethod
    def load_with_env(cls, env: EnvSettings | None = None) -> SettingsManager:
        env = env or EnvSettings()
        manager = cls.load(env.config)
        manager.apply_env_settings(env)
        return manager

    def apply_env_settings(self, env: EnvSettings) -> None:
        if env.out_dir is not None:
            self._settings.output.out_dir = env.out_dir
        if env.log_dir is not None:
            self._settings.logging.log_dir = env.log_dir

    def dump(self) -> None:
        data = self._settings.model_dump(by_alias=True, exclude_none=True)
        expanded = os.path.expanduser(self._path)
        parent = os.path.dirname(expanded)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(expanded, "wb") as file:
            tomli_w.dump(data, file)

    def get_settings(
        self,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> SettingsOut:
        data = self._settings.model_dump(include=include, exclude=exclude)
        return SettingsOut.model_validate(data)

    def find_task_settings(self, room_id: int) -> TaskSettings | None:
        for settings in self._settings.tasks:
            if settings.room_id == room_id:
                return settings
        return None

    def has_task_settings(self, room_id: int) -> bool:
        return self.find_task_settings(room_id) is not None
