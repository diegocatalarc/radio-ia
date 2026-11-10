import calendar
import hashlib
import logging
from dataclasses import dataclass, field, replace
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


MAX_BODY_CHARS = 8000
MIN_BODY_CHARS = 500
_BOT_WALL_PHRASES = ("enable javascript", "verify you are human", "captcha",
                     "subscribe to continue", "suscríbete para")


@dataclass
class FeedStats:
    """Feeds configurados que fallaron (error, XML roto) o no devolvieron entradas."""
    total: int = 0
    failed: int = 0
    failed_urls: list[str] = field(default_factory=list)


def _clean_body(text: str | None) -> str | None:
    text = (text or "").strip()
    if len(text) < MIN_BODY_CHARS:
        return None
    low = text.lower()
    if any(p in low for p in _BOT_WALL_PHRASES):
        return None
    return text[:MAX_BODY_CHARS]


def _extract_body(client, url: str) -> str | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text) if resp.text else None
    except Exception as exc:
        log.warning("article fetch failed for %s: %s", url, exc)
        return None
    return _clean_body(text)


def _new_client():
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                        headers={"User-Agent": USER_AGENT})


def collect_pool(feeds: list[str], since: datetime,
                 client=None) -> tuple[list[Story], FeedStats]:
    """Etapa 1: historias dentro de la ventana, solo titular y resumen (sin cuerpo)."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    own_client = client is None
    if own_client:
        client = _new_client()
    stories: list[Story] = []
    seen: set[str] = set()
    stats = FeedStats(total=len(feeds))

    def fail(feed_url: str) -> None:
        stats.failed += 1
        stats.failed_urls.append(feed_url)

    try:
        for feed_url in feeds:
            try:
                resp = client.get(feed_url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
            except Exception as exc:
                log.warning("feed failed %s: %s", feed_url, exc)
                fail(feed_url)
                continue
            if parsed.get("bozo") and not parsed.entries:
                log.warning(
                    "malformed feed %s: %s", feed_url, parsed.get("bozo_exception")
                )
                fail(feed_url)
                continue
            if not parsed.entries:
                log.warning("feed with 0 entries %s", feed_url)
                fail(feed_url)
                continue
            source = parsed.feed.get("title") or urlparse(feed_url).netloc
            for entry in parsed.entries:
                url = entry.get("link")
                try:
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
                        )
                    )
                except Exception as exc:
                    log.warning("entry failed %s: %s", url, exc)
    finally:
        if own_client:
            client.close()
    return stories, stats


def balance_pool(stories: list[Story], size: int) -> list[Story]:
    """Hasta ``size`` historias, repartidas en round-robin entre fuentes (la más
    reciente de cada una primero) para que un feed ruidoso no ocupe todos los
    huecos. El resultado queda ordenado de más nueva a más antigua."""
    by_source: dict[str, list[Story]] = {}
    for s in sorted(stories, key=lambda s: s.published, reverse=True):
        by_source.setdefault(s.source, []).append(s)
    picked: list[Story] = []
    queues = list(by_source.values())
    while queues and len(picked) < size:
        for q in queues:
            if len(picked) >= size:
                break
            picked.append(q.pop(0))
        queues = [q for q in queues if q]
    return sorted(picked, key=lambda s: s.published, reverse=True)


def fetch_bodies(stories: list[Story], client=None) -> list[Story]:
    """Etapa 2: descarga el cuerpo solo de las historias elegidas."""
    own_client = client is None
    if own_client:
        client = _new_client()
    try:
        return [replace(s, body=_extract_body(client, s.url)) for s in stories]
    finally:
        if own_client:
            client.close()


def fetch_stories(feeds: list[str], since: datetime, client=None) -> list[Story]:
    """Pool completo con cuerpos (conveniencia; el pipeline usa las dos etapas)."""
    own_client = client is None
    if own_client:
        client = _new_client()
    try:
        pool, _ = collect_pool(feeds, since, client=client)
        return fetch_bodies(pool, client=client)
    finally:
        if own_client:
            client.close()
