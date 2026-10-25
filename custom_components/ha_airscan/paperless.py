"""Minimal Paperless-ngx API client."""

from __future__ import annotations

import aiohttp
from aiohttp import ClientTimeout


class PaperlessError(Exception):
    """Generic Paperless error."""


class PaperlessAuthError(PaperlessError):
    """Token rejected."""


class PaperlessClient:
    """Upload documents to Paperless-ngx."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        }

    async def check(self) -> None:
        """Verify URL and token."""
        try:
            async with self._session.get(
                f"{self._url}/api/documents/?page_size=1",
                headers=self._headers,
                timeout=ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    raise PaperlessAuthError("Invalid token")
                if resp.status != 200:
                    raise PaperlessError(
                        f"HTTP {resp.status} von {self._url}/api/documents/ – URL/Port prüfen"
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PaperlessError(f"{type(err).__name__}: {err}") from err

    async def upload(
        self,
        pdf: bytes,
        filename: str,
        *,
        title: str | None = None,
        tags: list[str] | None = None,
        correspondent: str | None = None,
        document_type: str | None = None,
    ) -> str:
        """Upload a PDF, returns the Paperless task id."""
        form = aiohttp.FormData()
        form.add_field("document", pdf, filename=filename, content_type="application/pdf")
        if title:
            form.add_field("title", title)
        for tag in tags or []:
            form.add_field("tags", tag)
        if correspondent:
            form.add_field("correspondent", correspondent)
        if document_type:
            form.add_field("document_type", document_type)
        try:
            async with self._session.post(
                f"{self._url}/api/documents/post_document/",
                data=form,
                headers=self._headers,
                timeout=ClientTimeout(total=120),
            ) as resp:
                if resp.status in (401, 403):
                    raise PaperlessAuthError("Invalid token")
                if resp.status != 200:
                    raise PaperlessError(
                        f"Upload failed (HTTP {resp.status}): {(await resp.text())[:200]}"
                    )
                return (await resp.text()).strip().strip('"')
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PaperlessError(f"{type(err).__name__}: {err}") from err
