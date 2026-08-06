"""HTTP client for the fake-bili /_control endpoints."""

from __future__ import annotations

from typing import Any

import httpx


class FakeControl:
    """Drive the fake Bilibili server from outside its container."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=10)

    def close(self) -> None:
        self._client.close()

    def state(self) -> dict[str, Any]:
        return self._client.get("/_control/state").json()

    def set_live(self) -> None:
        self._client.post("/_control/live").raise_for_status()

    def set_offline(self) -> None:
        self._client.post("/_control/offline").raise_for_status()

    def set_fault(self, **faults: Any) -> None:
        resp = self._client.post("/_control/fault", json=faults)
        resp.raise_for_status()

    def clear_faults(self) -> None:
        self._client.post("/_control/clear-faults").raise_for_status()

    def cut_streams(self) -> int:
        """Abort every in-flight stream, the way a CDN outage does."""
        return int(self._client.post("/_control/stream/cut").json()["cut"])

    def send_danmaku(self, text: str, *, count: int = 1) -> None:
        self._client.post(
            "/_control/danmaku", json={"text": text, "count": count}
        ).raise_for_status()

    def send_command(self, cmd: str, data: dict[str, Any] | None = None) -> None:
        self._client.post(
            "/_control/command", json={"cmd": cmd, "data": data or {}}
        ).raise_for_status()
