"""Environment-variable settings that overlay the TOML configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from birec.setting.models import DEFAULT_SETTINGS_FILE

__all__ = ("EnvSettings",)


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BIREC_",
        str_strip_whitespace=True,
        extra="ignore",
    )

    config: str = DEFAULT_SETTINGS_FILE
    out_dir: str | None = None
    log_dir: str | None = None
