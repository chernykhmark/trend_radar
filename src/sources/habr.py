import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
import structlog

from src.schemas.post import RawPost
from src.sources.base import BaseSource

log = structlog.get_logger(__name__)

_ARTICLE_ID_RE = re.compile(r"/(?:articles|post|company/[^/]+/blog)/(\d+)")


class HabrSource(BaseSource):
    type = "habr"

    def __init__(self, name: str, params: dict[str, Any]) -> None:
        self.name = name
        self.params = params
        self.hub: str = params["hub"]
        self.min_rating: int | None = params.get("min_rating")
        self._rss_url = f"https://habr.com/ru/rss/hub/{self.hub}/all/?fl=ru"
        # User-Agent — некоторые CDN отдают 403 на дефолтный httpx
        self._headers = {"User-Agent": "trend-radar/0.1 (+https://habr.com)"}
        self._timeout = httpx.Timeout(15.0)

    async def fetch(self, since: datetime) -> list[RawPost]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        try:
            async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout, follow_redirects=True) as client:
                resp = await client.get(self._rss_url)
                resp.raise_for_status()
                body = resp.content
        except Exception:
            log.exception("habr.fetch_rss_failed", source=self.name, url=self._rss_url)
            return []

        parsed = await asyncio.to_thread(feedparser.parse, body)

        results: list[RawPost] = []
        for entry in parsed.entries:
            try:
                post = self._entry_to_post(entry)
            except Exception as e:
                log.warning("habr.entry_parse_failed", source=self.name, error=str(e))
                continue

            if post is None:
                continue
            if post.published_at <= since:
                continue
            results.append(post)

        log.info("habr.fetched", source=self.name, hub=self.hub, count=len(results))
        return results

    def _entry_to_post(self, entry: Any) -> RawPost | None:
        url = entry.get("link")
        if not url:
            return None

        external_id = self._extract_external_id(url)
        if not external_id:
            # fallback — guid
            external_id = entry.get("id") or url

        published_at = self._parse_pubdate(entry)
        if published_at is None:
            log.warning("habr.no_pubdate", url=url)
            return None

        title = (entry.get("title") or "").strip()
        author = entry.get("author") or None
        content = ""
        if "content" in entry and entry.content:
            content = entry.content[0].get("value", "") or ""
        if not content:
            content = entry.get("summary", "") or ""

        return RawPost(
            source_name=self.name,
            external_id=str(external_id),
            url=url,
            title=title,
            author=author,
            content=content,
            published_at=published_at,
            rating=None,  # из RSS рейтинг недоступен; HTML-парсинг отложен до явного запроса
            raw={
                "id": entry.get("id"),
                "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
                "summary": entry.get("summary"),
            },
        )

    @staticmethod
    def _extract_external_id(url: str) -> str | None:
        m = _ARTICLE_ID_RE.search(url)
        return m.group(1) if m else None

    @staticmethod
    def _parse_pubdate(entry: Any) -> datetime | None:
        raw = entry.get("published") or entry.get("updated")
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)