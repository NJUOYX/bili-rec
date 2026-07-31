"""Application, login, validation, and update endpoints (§7.3)."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import APIRouter, Request

from ... import __version__
from ..models import ResponseMessage

app_router = APIRouter(prefix="/api/v1", tags=["app"])

# Only transport failures are upstream's fault; anything else (a bug here, a
# contract change) must keep surfacing as a 500 so it is not mistaken for
# 「B 站不可达」.
_UPSTREAM_ERRORS = (aiohttp.ClientError, TimeoutError, OSError)


# ── App status/info/restart/exit ─────────────────────────────────────────────


@app_router.get("/app/status")
async def get_app_status(request: Request) -> dict[str, Any]:
    """Get application runtime status."""
    from birec.task import RunningStatus

    application = request.app.state.application
    task_manager = request.app.state.task_manager
    tasks = task_manager.get_all_tasks()
    data = {
        "started": application.is_started,
        "task_count": len(tasks),
        "recording_count": sum(
            1 for t in tasks if t.running_status == RunningStatus.RECORDING
        ),
    }
    return ResponseMessage(data=data).to_dict()


@app_router.get("/app/info")
async def get_app_info() -> dict[str, Any]:
    """Get application info."""
    data = {
        "name": "bili-rec",
        "version": __version__,
        "python": sys.version.split()[0],
        "pid": os.getpid(),
    }
    return ResponseMessage(data=data).to_dict()


@app_router.post("/app/restart")
async def restart_app() -> dict[str, Any]:
    """Restart the application process (sends SIGHUP to self)."""
    os.kill(os.getpid(), signal.SIGHUP)
    return ResponseMessage(message="Restarting...").to_dict()


@app_router.post("/app/exit")
async def exit_app() -> dict[str, Any]:
    """Gracefully exit the application (sends SIGTERM to self)."""
    os.kill(os.getpid(), signal.SIGTERM)
    return ResponseMessage(message="Exiting...").to_dict()


# ── QR code login ────────────────────────────────────────────────────────────


@app_router.get("/qrcode/login")
async def qrcode_login(request: Request) -> dict[str, Any]:
    """Request a TV login QR code from Bilibili."""
    from birec.bili.api import AppApi

    try:
        api: AppApi = request.app.state.bili_api
    except AttributeError:
        return ResponseMessage(code=503, message="Bili API not initialized").to_dict()

    try:
        result = await api.request_tv_qrcode()
    except _UPSTREAM_ERRORS as e:
        # Bilibili's passport host is the only way to mint a code; a network
        # failure is upstream's, so report it instead of a bare 500.
        return ResponseMessage(
            code=502, message=f"Failed to request QR code: {e}"
        ).to_dict()
    return ResponseMessage(data=result).to_dict()


@app_router.post("/qrcode/login/poll")
async def qrcode_login_poll(request: Request) -> dict[str, Any]:
    """Poll TV QR code login status and write cookie on success."""
    from birec.bili.api import AppApi

    try:
        api: AppApi = request.app.state.bili_api
    except AttributeError:
        return ResponseMessage(code=503, message="Bili API not initialized").to_dict()

    body: dict[str, Any] = await request.json()
    auth_code = body.get("auth_code", "")
    if not auth_code:
        return ResponseMessage(code=400, message="auth_code is required").to_dict()

    try:
        result = await api.poll_tv_qrcode(auth_code)
    except _UPSTREAM_ERRORS as e:
        return ResponseMessage(code=502, message=f"Failed to poll login: {e}").to_dict()
    code_val = result.get("code", -1)

    if code_val == 0:
        # Login success - extract and store cookie
        data = result.get("data", {})
        token_info = data.get("token_info", {})
        cookies = data.get("cookie_info", {}).get("cookies", [])
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        # Update settings header cookie
        manager = request.app.state.settings_manager
        manager.settings.header.cookie = cookie_str
        manager.dump()
        return ResponseMessage(
            message="Login successful",
            data={
                "access_token": token_info.get("access_token", ""),
                "cookie": cookie_str,
            },
        ).to_dict()

    return ResponseMessage(
        code=code_val,
        message=result.get("message", "Login pending"),
        data=result.get("data"),
    ).to_dict()


# ── Validation ───────────────────────────────────────────────────────────────


@app_router.post("/validation/dir")
async def validate_dir(request: Request) -> dict[str, Any]:
    """Validate that a directory path is readable and writable."""
    body: dict[str, Any] = await request.json()
    path_str = body.get("path", "")
    if not path_str:
        return ResponseMessage(code=400, message="path is required").to_dict()

    path = Path(os.path.expanduser(path_str))
    errors: list[str] = []

    if not path.exists():
        errors.append(f"Path does not exist: {path}")
    elif not path.is_dir():
        errors.append(f"Not a directory: {path}")
    else:
        if not os.access(path, os.R_OK):
            errors.append(f"Not readable: {path}")
        if not os.access(path, os.W_OK):
            errors.append(f"Not writable: {path}")

    if errors:
        return ResponseMessage(code=400, message="; ".join(errors)).to_dict()

    return ResponseMessage(
        message="Directory is valid", data={"path": str(path)}
    ).to_dict()


# ── Update ───────────────────────────────────────────────────────────────────


@app_router.get("/update/version/latest")
async def get_latest_version(request: Request) -> dict[str, Any]:
    """Get the latest version from PyPI."""
    import aiohttp

    from birec.update import PypiApi

    try:
        async with aiohttp.ClientSession() as session:
            api = PypiApi(session)
            version = await api.get_latest_version_string("birec")
    except Exception as e:
        return ResponseMessage(code=502, message=f"Failed to query PyPI: {e}").to_dict()

    if version is None:
        return ResponseMessage(code=404, message="Project not found on PyPI").to_dict()

    return ResponseMessage(data={"version": version, "current": __version__}).to_dict()
