"""Domain exceptions for HTTP error mapping."""

from __future__ import annotations

__all__ = ("NotFoundError", "ExistsError", "ForbiddenError")


class NotFoundError(ValueError):
    """Resource not found (HTTP 404)."""


class ExistsError(ValueError):
    """Resource already exists (HTTP 409)."""


class ForbiddenError(Exception):
    """Access forbidden (HTTP 403)."""
