"""End-to-end Web API verification against a real live room.

Wires a ``RecordTaskManager`` with a real task factory into a fresh FastAPI app
and drives the task lifecycle purely over HTTP (add → query → refresh info →
delete), asserting the envelope contract and that a real ``Live.refresh()``
performed through the API populates room/user metadata.

Monitoring and recording are left disabled in the factory so the HTTP surface
is exercised deterministically without spawning unbounded background stream /
danmaku loops. The application-level wiring gap (``create_application`` builds a
``RecordTaskManager`` without a task factory) is tracked separately; this test
demonstrates the endpoints behave correctly once a factory is supplied.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import aiohttp
import httpx
from httpx import ASGITransport

from birec.bili.danmaku_client import DanmakuClient
from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor
from birec.core.path_provider import PathProvider
from birec.core.recorder import Recorder
from birec.postprocess.postprocessor import Postprocessor
from birec.task import RecordTask, RecordTaskManager
from birec.web import create_app

_PREFIX = "/api/v1/tasks"


def _make_factory(
    session: aiohttp.ClientSession, cookie: str, out_dir: Path
) -> Callable[[int], RecordTask]:
    def factory(room_id: int) -> RecordTask:
        live = Live(room_id, session=session)
        if cookie:
            live.cookie = cookie
        danmaku_client = DanmakuClient(room_id, session=session, cookie=cookie)
        monitor = LiveMonitor(live)
        path_provider = PathProvider(str(out_dir), "{roomid}/{roomid}")
        recorder = Recorder(room_id, live, monitor, session, path_provider)
        postprocessor = Postprocessor(
            remux_enabled=False, inject_metadata_enabled=False
        )
        return RecordTask(
            room_id,
            live,
            danmaku_client,
            monitor,
            recorder,
            postprocessor,
            enable_monitor=False,
            enable_recorder=False,
        )

    return factory


class TestWebApiEndToEnd:
    async def test_task_lifecycle_over_http(
        self,
        bili_session: aiohttp.ClientSession,
        bili_cookie: str,
        live_room_id: int,
        tmp_path: Path,
    ) -> None:
        app = create_app()
        manager = RecordTaskManager(
            task_factory=_make_factory(bili_session, bili_cookie, tmp_path)
        )
        app.state.task_manager = manager
        await manager.start()

        transport = ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                # Add the task.
                res = await client.post(
                    f"{_PREFIX}/{live_room_id}", json={"room_id": live_room_id}
                )
                assert res.status_code == 200
                body = res.json()
                assert body["code"] == 0, body
                assert body["data"]["room_id"] == live_room_id

                # It appears in the task listing.
                res = await client.get(f"{_PREFIX}/data")
                assert res.status_code == 200
                listing = res.json()
                assert listing["code"] == 0
                room_ids = [t["room_id"] for t in listing["data"]]
                assert live_room_id in room_ids

                # Refresh info triggers a real Live.refresh() through the API.
                res = await client.post(f"{_PREFIX}/{live_room_id}/info")
                assert res.status_code == 200
                assert res.json()["code"] == 0

                # Single-task data is populated after the refresh.
                res = await client.get(f"{_PREFIX}/{live_room_id}/data")
                assert res.status_code == 200
                data = res.json()
                assert data["code"] == 0
                assert data["data"]["room_id"] == live_room_id
                assert data["data"]["user_name"], "user name not populated"

                # Delete the task.
                res = await client.delete(f"{_PREFIX}/{live_room_id}")
                assert res.status_code == 200
                assert res.json()["code"] == 0

                # It is gone from the listing.
                res = await client.get(f"{_PREFIX}/data")
                room_ids = [t["room_id"] for t in res.json()["data"]]
                assert live_room_id not in room_ids
        finally:
            await manager.stop()
