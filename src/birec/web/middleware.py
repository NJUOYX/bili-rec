"""Web middleware: Brotli compression, BaseHref, RouteRedirect (§5.14)."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

__all__ = ("BaseHrefMiddleware", "RouteRedirectMiddleware")


class BaseHrefMiddleware(BaseHTTPMiddleware):
    """Inject ``<base href="...">`` into HTML responses for reverse-proxy sub-path.

    When the app is served under a sub-path (e.g. ``/birec/``), the frontend
    needs a ``<base>`` tag so relative asset URLs resolve correctly.
    """

    def __init__(self, app: Any, base_href: str = "/") -> None:
        super().__init__(app)
        self._base_href = base_href.rstrip("/") + "/"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return response

        # Read body, inject base tag after <head>
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        base_tag = f'<base href="{self._base_href}">'.encode()
        # Insert after <head> or <head ...>
        lower_body = body.lower()
        head_end = lower_body.find(b"<head>")
        if head_end != -1:
            insert_pos = head_end + len(b"<head>")
            body = body[:insert_pos] + base_tag + body[insert_pos:]
        else:
            # Try <head ...> with attributes
            head_start = lower_body.find(b"<head")
            if head_start != -1:
                tag_end = body.find(b">", head_start)
                if tag_end != -1:
                    insert_pos = tag_end + 1
                    body = body[:insert_pos] + base_tag + body[insert_pos:]

        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


class RouteRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect non-API routes to ``index.html`` for SPA frontend routing.

    Any GET request that:
    - does NOT start with ``/api/`` or ``/ws/``
    - does NOT have a file extension (e.g. ``.js``, ``.css``)
    - accepts ``text/html``

    is redirected to ``/index.html`` so the frontend router can handle it.
    """

    def __init__(self, app: Any, index_path: str = "/index.html") -> None:
        super().__init__(app)
        self._index_path = index_path

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip API, WebSocket, and static asset paths
        if path.startswith(("/api/", "/ws/")):
            return await call_next(request)

        # Skip paths with file extensions (static assets)
        if "." in path.split("/")[-1]:
            return await call_next(request)

        # Only redirect GET requests that accept HTML
        if request.method != "GET":
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" not in accept:
            return await call_next(request)

        # Try the original path first
        response = await call_next(request)

        # If 404, redirect to index.html for SPA routing
        if response.status_code == 404:
            from starlette.responses import RedirectResponse

            return RedirectResponse(self._index_path, status_code=302)

        return response
