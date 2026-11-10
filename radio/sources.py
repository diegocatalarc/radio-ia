import calendar
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
import trafilatura

from radio.models import Story

log = logging.getLogger(__name__)

TIMEOUT = 15.0
USER_AGENT = "radio-ia/0.1 (+news podcast pipeline)"


def story_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def _extract_body(client, url: str) -> str | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text) if resp.text else None
    except Exception as exc:
        log.warning("article fetch failed for %s: %s", url, exc)
        return None
    text = (text or "").strip()
    return text or None


def fetch_stories(feeds: list[str], since: datetime, client=None) -> list[Story]:
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    own_client = client is None
    if own_client:
        client = httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    stories: list[Story] = []
    seen: set[str] = set()
    try:
        for feed_url in feeds:
            try:
                resp = client.get(feed_url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
                source = parsed.feed.get("title") or urlparse(feed_url).netloc
                for entry in parsed.entries:
                    url = entry.get("link")
                    published = _published(entry)
                    if not url or published is None or published < since:
                        continue
                    sid = story_id(url)
                    if sid in seen:
                        continue
                    seen.add(sid)
                    stories.append(
                        Story(
                            id=sid,
                            title=entry.get("title", "").strip(),
                            url=url,
                            source=source,
                            published=published,
                            summary=entry.get("summary", "").strip(),
                            body=_extract_body(client, url),
                        )
                    )
            except Exception as exc:
                log.warning("feed failed %s: %s", feed_url, exc)
    finally:
        if own_client:
            client.close()
    return stories
