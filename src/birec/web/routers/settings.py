"""Settings API endpoints (§7.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import ValidationError

from birec.setting.models import SettingsIn, TaskOptions

from ..models import ResponseMessage

settings_router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _get_settings_manager(request: Request) -> Any:
    return request.app.state.settings_manager


@settings_router.get("")
async def get_settings(request: Request) -> dict[str, Any]:
    """Get global settings with optional include/exclude filters."""
    manager = _get_settings_manager(request)
    include_param = request.query_params.get("include")
    exclude_param = request.query_params.get("exclude")
    include = set(include_param.split(",")) if include_param else None
    exclude = set(exclude_param.split(",")) if exclude_param else None
    settings_out = manager.get_settings(include=include, exclude=exclude)
    data = settings_out.model_dump(mode="json", exclude_none=True, by_alias=True)
    return ResponseMessage(data=data).to_dict()


@settings_router.patch("")
async def patch_settings(request: Request) -> dict[str, Any]:
    """Update global settings. Triggers danmaku client reconnect on header change."""
    manager = _get_settings_manager(request)
    body: dict[str, Any] = await request.json()

    try:
        settings_in = SettingsIn.model_validate(body)
    except ValidationError as e:
        return ResponseMessage(
            code=422, message=f"Validation error: {e.error_count()} field(s)"
        ).to_dict()

    # Apply non-None fields to the live settings
    current = manager.settings
    for field_name, value in settings_in.model_dump(exclude_none=True).items():
        if hasattr(current, field_name):
            section = getattr(current, field_name)
            if isinstance(value, dict):
                for k, v in value.items():
                    if hasattr(section, k):
                        setattr(section, k, v)

    # Persist to disk
    manager.dump()

    # Hot-update output directory on existing tasks so that future recordings
    # land in the new location immediately (fixes #6).
    patch_data = settings_in.model_dump(exclude_none=True)
    output_patch = patch_data.get("output")
    if output_patch and "out_dir" in output_patch:
        new_out_dir: str = current.output.out_dir
        task_manager = request.app.state.task_manager
        for task in task_manager.get_all_tasks():
            task.update_out_dir(new_out_dir)

    # Same for the post-processing switches: a task keeps the ones it was built
    # with, so without this turning danmaku→ASS on would only apply to rooms
    # added afterwards.
    if patch_data.get("postprocessing"):
        request.app.state.application.refresh_postprocessing_options()

    # Logging changes (log_dir, console_log_level, backup_count) take effect
    # immediately so the user does not have to restart the server (#29).
    if patch_data.get("logging"):
        request.app.state.application.refresh_logging()

    data = manager.get_settings().model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    return ResponseMessage(message="Settings updated", data=data).to_dict()


@settings_router.get("/tasks/{room_id}")
async def get_task_settings(request: Request, room_id: int) -> dict[str, Any]:
    """Get task-level settings (null fields fall back to global)."""
    manager = _get_settings_manager(request)
    task_settings = manager.find_task_settings(room_id)
    if task_settings is None:
        return ResponseMessage(
            code=404, message=f"Task settings for room {room_id} not found"
        ).to_dict()
    data = task_settings.model_dump(mode="json", by_alias=True)
    return ResponseMessage(data=data).to_dict()


@settings_router.patch("/tasks/{room_id}")
async def patch_task_settings(request: Request, room_id: int) -> dict[str, Any]:
    """Update task-level settings. Null fields fall back to global."""
    manager = _get_settings_manager(request)
    task_settings = manager.find_task_settings(room_id)
    if task_settings is None:
        return ResponseMessage(
            code=404, message=f"Task settings for room {room_id} not found"
        ).to_dict()

    body: dict[str, Any] = await request.json()

    try:
        options = TaskOptions.model_validate(body)
    except ValidationError as e:
        return ResponseMessage(
            code=422, message=f"Validation error: {e.error_count()} field(s)"
        ).to_dict()

    # Apply non-None option fields to the task settings
    option_patch = options.model_dump(exclude_none=True)
    for section_name, section_value in option_patch.items():
        if isinstance(section_value, dict):
            task_section = getattr(task_settings, section_name)
            for k, v in section_value.items():
                if hasattr(task_section, k):
                    setattr(task_section, k, v)

    # Also handle enable_monitor / enable_recorder if provided
    if "enable_monitor" in body:
        task_settings.enable_monitor = bool(body["enable_monitor"])
    if "enable_recorder" in body:
        task_settings.enable_recorder = bool(body["enable_recorder"])

    manager.dump()

    # Reach the task that is already running, not just the next one built.
    if option_patch.get("postprocessing"):
        request.app.state.application.refresh_postprocessing_options()

    data = task_settings.model_dump(mode="json", by_alias=True)
    return ResponseMessage(message="Task settings updated", data=data).to_dict()
