"""Update checker: query PyPI for latest version."""

from __future__ import annotations

import logging

import aiohttp

__all__ = ("PypiApi",)

logger = logging.getLogger(__name__)

PYPI_JSON_URL = "https://pypi.org/pypi/{project}/json"


class PypiApi:
    """Query PyPI for project metadata and latest version."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        timeout: float = 10.0,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def get_latest_version_string(self, project: str) -> str | None:
        """Get the latest version string for a PyPI project.

        Args:
            project: PyPI project name (e.g., "birec").

        Returns:
            Latest version string, or None if query fails.
        """
        url = PYPI_JSON_URL.format(project=project)
        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                if resp.status != 200:
                    logger.warning(
                        "PyPI query failed for %s: HTTP %d", project, resp.status
                    )
                    return None
                data = await resp.json()
                info = data.get("info", {})
                version: str | None = info.get("version")
                if version:
                    logger.debug("Latest version of %s: %s", project, version)
                return version
        except Exception as e:
            logger.warning("Failed to query PyPI for %s: %s", project, e)
            return None

    async def get_project_info(self, project: str) -> dict[str, object] | None:
        """Get full project info from PyPI.

        Args:
            project: PyPI project name.

        Returns:
            Project info dict, or None if query fails.
        """
        url = PYPI_JSON_URL.format(project=project)
        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("info")  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Failed to query PyPI for %s: %s", project, e)
            return None
