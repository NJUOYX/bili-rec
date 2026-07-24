"""Helpers to overlay one settings model onto another in place."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ("update_settings", "shadow_settings", "overwrite_settings")


def update_settings[T: BaseModel](src: T, dst: T) -> None:
    """Copy only explicitly-set fields from ``src`` onto ``dst``."""
    overwrite_settings(src, dst, exclude_unset=True)


def shadow_settings[T: BaseModel](src: T, dst: T) -> None:
    """Copy only non-None fields from ``src`` onto ``dst`` (null falls back)."""
    overwrite_settings(src, dst, exclude_none=True)


def overwrite_settings[T: BaseModel](
    src: T, dst: T, exclude_unset: bool = False, exclude_none: bool = False
) -> None:
    assert isinstance(src, BaseModel) and isinstance(dst, BaseModel)

    names = src.model_fields_set if exclude_unset else set(type(src).model_fields)

    for name in names:
        if not hasattr(dst, name):
            continue
        value = getattr(src, name)
        if exclude_none and value is None:
            continue
        if isinstance(value, BaseModel):
            overwrite_settings(
                value,
                getattr(dst, name),
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
            )
        else:
            setattr(dst, name, value)
