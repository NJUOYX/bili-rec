"""Task API endpoints (§7.1).

Provides CRUD and control operations for record tasks, wired to the
``RecordTaskManager`` stored in ``app.state.task_manager``.

Route ordering: fixed-path batch endpoints are registered BEFORE
``/{room_id}`` parameterised routes so FastAPI matches them correctly.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from ...bili.exceptions import ApiRequestError
from ...task import RecordTaskManager, RunningStatus, TaskData
from ..models import ResponseMessage

__all__ = ("router",)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


# ── Request models ────────────────────────────────────────────────────────────


class AddTaskRequest(BaseModel):
    """Request body for adding a task.

    The room is always written to the config file, so the task survives a
    restart and has task-level options to patch. ``auto_enable`` decides
    whether monitoring and recording start enabled (§5.2).
    """

    room_id: int
    auto_enable: bool = True


class BatchRoomIds(BaseModel):
    """Request body for batch operations on specific rooms."""

    room_ids: list[int] = []


class BatchStopRequest(BaseModel):
    """Request body for batch stop with options."""

    room_ids: list[int] = []
    force: bool = False
    background: bool = False


class DeleteTasksRequest(BaseModel):
    """Request body for batch delete."""

    room_ids: list[int]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_manager(request: Request) -> RecordTaskManager:
    """Extract the RecordTaskManager from app state."""
    manager: RecordTaskManager = request.app.state.task_manager
    return manager


def _ok(data: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
    return ResponseMessage(code=0, message=message, data=data).to_dict()


def _task_data_to_dict(td: TaskData) -> dict[str, Any]:
    """Convert TaskData to a JSON-serialisable dict."""
    d = asdict(td)
    # Enum → value
    d["task_status"]["running_status"] = td.task_status.running_status.value
    return d


def _filter_tasks(
    tasks: list[TaskData],
    select: str | None,
) -> list[TaskData]:
    """Filter task data list by the ``select`` query parameter."""
    if not select or select == "all":
        return tasks

    result: list[TaskData] = []
    for td in tasks:
        if _matches_filter(td, select):
            result.append(td)
    return result


def _matches_filter(td: TaskData, select: str) -> bool:
    """Check if a task matches the given filter."""
    if select == "preparing":
        return not td.live_status
    if select == "living":
        return td.live_status
    if select == "monitor_enabled":
        return td.task_status.monitor_enabled
    if select == "monitor_disabled":
        return not td.task_status.monitor_enabled
    if select == "recorder_enabled":
        return td.task_status.recorder_enabled
    if select == "recorder_disabled":
        return not td.task_status.recorder_enabled
    if select in ("stopped", "waiting", "recording", "remuxing", "injecting"):
        return td.task_status.running_status == RunningStatus(select)
    return False


# ── GET /tasks/data (fixed path, before /{room_id}) ──────────────────────────


@router.get("/data")
async def get_tasks_data(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    select: str | None = Query(None),
) -> dict[str, Any]:
    """Get paginated task data with optional filtering."""
    manager = _get_manager(request)
    all_data = manager.get_all_task_data()
    filtered = _filter_tasks(all_data, select)
    total = len(filtered)
    start = (page - 1) * size
    end = start + size
    page_data = filtered[start:end]
    return _ok(
        {
            "total": total,
            "page": page,
            "size": size,
            "tasks": [_task_data_to_dict(td) for td in page_data],
        }
    )


# ── POST batch endpoints (fixed paths, BEFORE /{room_id}) ────────────────────


@router.post("/info")
async def batch_refresh_info(request: Request) -> dict[str, Any]:
    """Refresh info for all tasks."""
    manager = _get_manager(request)
    await manager.batch_refresh_info()
    return _ok(message="Info refreshed")


@router.post("/start")
async def batch_start(
    request: Request, body: BatchRoomIds | None = None
) -> dict[str, Any]:
    """Start monitoring for specified or all tasks."""
    manager = _get_manager(request)
    if body and body.room_ids:
        for rid in body.room_ids:
            task = manager.get_task(rid)
            if task:
                await task.enable_monitor()
    else:
        for task in manager.get_all_tasks():
            await task.enable_monitor()
    return _ok(message="Started")


@router.post("/stop")
async def batch_stop(
    request: Request, body: BatchStopRequest | None = None
) -> dict[str, Any]:
    """Stop monitoring for specified or all tasks."""
    manager = _get_manager(request)
    if body and body.room_ids:
        for rid in body.room_ids:
            task = manager.get_task(rid)
            if task:
                await task.disable_monitor()
    else:
        for task in manager.get_all_tasks():
            await task.disable_monitor()
    return _ok(message="Stopped")


@router.post("/recorder/enable")
async def batch_enable_recorder(
    request: Request, body: BatchRoomIds | None = None
) -> dict[str, Any]:
    """Enable recorder for specified or all tasks."""
    manager = _get_manager(request)
    if body and body.room_ids:
        for rid in body.room_ids:
            task = manager.get_task(rid)
            if task:
                task.enable_recorder()
    else:
        for task in manager.get_all_tasks():
            task.enable_recorder()
    return _ok(message="Recorder enabled")


@router.post("/recorder/disable")
async def batch_disable_recorder(
    request: Request, body: BatchRoomIds | None = None
) -> dict[str, Any]:
    """Disable recorder for specified or all tasks."""
    manager = _get_manager(request)
    if body and body.room_ids:
        for rid in body.room_ids:
            task = manager.get_task(rid)
            if task:
                await task.disable_recorder()
    else:
        for task in manager.get_all_tasks():
            await task.disable_recorder()
    return _ok(message="Recorder disabled")


# ── DELETE batch (fixed path) ────────────────────────────────────────────────


@router.delete("")
async def delete_tasks(request: Request, body: DeleteTasksRequest) -> dict[str, Any]:
    """Delete multiple tasks."""
    manager = _get_manager(request)
    errors: list[str] = []
    for rid in body.room_ids:
        try:
            await manager.remove_task(rid)
        except KeyError:
            errors.append(f"Task {rid} not found")
    if errors:
        return ResponseMessage(code=404, message="; ".join(errors)).to_dict()
    return _ok(message="Deleted")


# ── GET /{room_id}/* endpoints ───────────────────────────────────────────────


@router.get("/{room_id}/data")
async def get_task_data(request: Request, room_id: int) -> dict[str, Any]:
    """Get data for a single task."""
    manager = _get_manager(request)
    try:
        td = manager.get_task_data(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(_task_data_to_dict(td))


@router.get("/{room_id}/param")
async def get_task_param(request: Request, room_id: int) -> dict[str, Any]:
    """Get task parameters."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    param = task.get_param()
    return _ok(asdict(param))


@router.get("/{room_id}/metadata")
async def get_task_metadata(request: Request, room_id: int) -> dict[str, Any]:
    """Get recording metadata for a task."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    metadata = task.get_metadata()
    return _ok(asdict(metadata))


@router.get("/{room_id}/profile")
async def get_task_profile(request: Request, room_id: int) -> dict[str, Any]:
    """Get current stream ffprobe profile."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    profile = task.get_profile()
    return _ok(profile)


@router.get("/{room_id}/videos")
async def get_task_videos(request: Request, room_id: int) -> dict[str, Any]:
    """Get video file details for a task."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    videos = task.get_videos()
    return _ok({"videos": [asdict(v) for v in videos]})


@router.get("/{room_id}/danmakus")
async def get_task_danmakus(request: Request, room_id: int) -> dict[str, Any]:
    """Get danmaku file details for a task."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    danmakus = task.get_danmakus()
    return _ok({"danmakus": [asdict(d) for d in danmakus]})


# ── POST /{room_id}/* endpoints ──────────────────────────────────────────────


@router.post("/{room_id}/info")
async def refresh_task_info(request: Request, room_id: int) -> dict[str, Any]:
    """Refresh info for a single task."""
    manager = _get_manager(request)
    task = manager.get_task(room_id)
    if task is None:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    await task.refresh_info()
    return _ok(message="Info refreshed")


@router.post("/{room_id}/start")
async def start_task(request: Request, room_id: int) -> dict[str, Any]:
    """Start monitoring for a task."""
    manager = _get_manager(request)
    try:
        await manager.start_task(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(message="Started")


@router.post("/{room_id}/stop")
async def stop_task(request: Request, room_id: int) -> dict[str, Any]:
    """Stop monitoring for a task."""
    manager = _get_manager(request)
    try:
        await manager.stop_task(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(message="Stopped")


@router.post("/{room_id}/recorder/enable")
async def enable_recorder(request: Request, room_id: int) -> dict[str, Any]:
    """Enable recorder for a task."""
    manager = _get_manager(request)
    try:
        manager.enable_recorder(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(message="Recorder enabled")


@router.post("/{room_id}/recorder/disable")
async def disable_recorder(request: Request, room_id: int) -> dict[str, Any]:
    """Disable recorder for a task."""
    manager = _get_manager(request)
    try:
        await manager.disable_recorder(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(message="Recorder disabled")


# ── POST /{room_id} (add task — MUST be after all fixed POST paths) ──────────


@router.post("/{room_id}")
async def add_task(request: Request, body: AddTaskRequest) -> dict[str, Any]:
    """Add a new task for a room."""
    manager = _get_manager(request)
    try:
        task = await manager.add_task(body.room_id, auto_enable=body.auto_enable)
    except ValueError as exc:
        return ResponseMessage(code=409, message=str(exc)).to_dict()
    except ApiRequestError as exc:
        # Bilibili refused to tell us about the room. Without its info there is
        # no task to build, and the caller needs to hear that as an answer
        # rather than as a 500 from a stray exception.
        return ResponseMessage(
            code=502, message=f"Bilibili API error: {exc.message or exc.code}"
        ).to_dict()
    except RuntimeError as exc:
        return ResponseMessage(code=500, message=str(exc)).to_dict()
    return _ok({"room_id": task.room_id}, message="Task added")


# ── DELETE /{room_id} ────────────────────────────────────────────────────────


@router.delete("/{room_id}")
async def delete_task(request: Request, room_id: int) -> dict[str, Any]:
    """Delete a single task."""
    manager = _get_manager(request)
    try:
        await manager.remove_task(room_id)
    except KeyError:
        return ResponseMessage(code=404, message=f"Task {room_id} not found").to_dict()
    return _ok(message="Deleted")
