"""TOML-backed settings manager with environment overlay."""

from __future__ import annotations

import os
import tomllib
from typing import Any

import tomli_w

from birec.setting.env import EnvSettings
from birec.setting.helpers import shadow_settings
from birec.setting.models import BaseModel, Settings, SettingsOut, TaskSettings

__all__ = ("SettingsManager",)

_TASK_SECTIONS: tuple[str, ...] = (
    "output",
    "header",
    "danmaku",
    "recorder",
    "postprocessing",
)


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

    def add_task_settings(
        self,
        room_id: int,
        *,
        enable_monitor: bool = True,
        enable_recorder: bool = True,
    ) -> TaskSettings:
        """Register a room in the config, or return the existing entry.

        The config is the source of truth for tasks: an added task only
        survives a restart, and only has task-level options to read or patch,
        once it has an entry here. An existing entry is returned untouched so
        restoring tasks at startup never overwrites the user's overrides.
        """
        existing = self.find_task_settings(room_id)
        if existing is not None:
            return existing
        settings = TaskSettings(
            room_id=room_id,
            enable_monitor=enable_monitor,
            enable_recorder=enable_recorder,
        )
        self._settings.tasks.append(settings)
        return settings

    def remove_task_settings(self, room_id: int) -> None:
        """Drop a room's config entry; a room without one is left alone."""
        self._settings.tasks = [
            settings for settings in self._settings.tasks if settings.room_id != room_id
        ]

    def resolve_task_settings(self, room_id: int) -> dict[str, BaseModel]:
        """Merge a task's per-section options over the global settings.

        Task option fields left as ``None`` fall back to the global value.
        The global settings are not mutated.
        """
        task = self.find_task_settings(room_id)
        if task is None:
            raise ValueError(f"task settings of room {room_id} not found")

        resolved: dict[str, BaseModel] = {}
        for name in _TASK_SECTIONS:
            effective = getattr(self._settings, name).model_copy(deep=True)
            shadow_settings(getattr(task, name), effective)
            resolved[name] = effective
        return resolved
