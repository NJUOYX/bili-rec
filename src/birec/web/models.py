"""Web layer shared models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ("ResponseMessage",)


@dataclass(frozen=True, slots=True)
class ResponseMessage:
    """Unified API response body."""

    code: int = 0
    message: str = ""
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result
