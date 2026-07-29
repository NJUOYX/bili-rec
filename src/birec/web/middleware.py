"""Web middleware: Brotli compression, BaseHref, RouteRedirect (§5.14)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response

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
            headers=self._headers_without_length(response),
            media_type=response.media_type,
        )

    @staticmethod
    def _headers_without_length(response: Response) -> dict[str, str]:
        """Copy headers minus ``content-length``, which injection invalidates.

        ``Response`` only computes ``content-length`` when absent from the
        given headers, so passing the upstream value through would understate
        the injected body and make real clients truncate the document.
        """
        return {
            key: value
            for key, value in response.headers.items()
            if key.lower() != "content-length"
        }


class RouteRedirectMiddleware(BaseHTTPMiddleware):
    """Serve ``index.html`` in place for SPA deep links (§12).

    Any GET request that:
    - does NOT start with ``/api/`` or ``/ws/``
    - does NOT have a file extension (e.g. ``.js``, ``.css``)
    - accepts ``text/html``

    and 404s downstream is answered with the SPA entry document **at the
    originally requested URL** (HTTP 200). Redirecting to ``/index.html``
    instead would discard the deep link, leaving the client-side router with
    no way to restore the requested route on refresh or bookmark entry.
    """

    def __init__(self, app: Any, index_file: Path | str) -> None:
        super().__init__(app)
        self._index_file = Path(index_file)

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

        # Only rewrite GET requests that accept HTML
        if request.method != "GET":
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" not in accept:
            return await call_next(request)

        # Try the original path first
        response = await call_next(request)

        # Unknown route → hand the SPA shell back without changing the URL.
        if response.status_code == 404 and self._index_file.is_file():
            return FileResponse(
                self._index_file, status_code=200, media_type="text/html"
            )

        return response
