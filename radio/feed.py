"""Podcast RSS 2.0 feed (with iTunes tags) and episode list management."""
import posixpath
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time
from email.utils import format_datetime
from zoneinfo import ZoneInfo

MAX_EPISODES = 60
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CHANNEL_TITLE = "Radio IA"
CHANNEL_DESCRIPTION = "Resumen diario en español sobre inteligencia artificial y su impacto económico."
CHANNEL_AUTHOR = "Radio IA"


@dataclass(frozen=True)
class Episode:
    """One episode.

    ``mp3_path`` is the file path of the audio; only its basename is used and the
    public URL is ``{site_url}/episodes/{basename}`` (episodes are published under
    an ``episodes/`` directory at the site root).
    """
    day: date
    title: str
    description: str
    mp3_path: str
    duration_s: int
    size_bytes: int
    published: datetime | None = None  # tz-aware generation time; used verbatim for pubDate


def _enclosure_url(site_url: str, mp3_path: str) -> str:
    return f"{site_url.rstrip('/')}/episodes/{posixpath.basename(mp3_path)}"


_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _clean(text: str) -> str:
    """Drop characters that are illegal in XML 1.0."""
    return _ILLEGAL_XML.sub("", text)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = _clean(text)
    return el


def build_feed(episodes: list[Episode], site_url: str, tz: str, publish_hour: int = 2) -> str:
    """pubDate: ``Episode.published`` verbatim if set, else the day at ``publish_hour`` in ``tz``."""
    ET.register_namespace("itunes", ITUNES_NS)
    zone = ZoneInfo(tz)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    _sub(channel, "title", CHANNEL_TITLE)
    _sub(channel, "link", site_url.rstrip("/") + "/")
    _sub(channel, "description", CHANNEL_DESCRIPTION)
    _sub(channel, "language", "es")
    _sub(channel, f"{{{ITUNES_NS}}}author", CHANNEL_AUTHOR)
    _sub(channel, f"{{{ITUNES_NS}}}explicit", "false")
    for e in episodes:
        item = ET.SubElement(channel, "item")
        _sub(item, "title", e.title)
        _sub(item, "description", e.description)
        _sub(item, "guid", e.day.isoformat(), isPermaLink="false")
        published = e.published or datetime.combine(e.day, time(publish_hour), tzinfo=zone)
        _sub(item, "pubDate", format_datetime(published))
        _sub(item, "enclosure", url=_enclosure_url(site_url, e.mp3_path),
             length=str(e.size_bytes), type="audio/mpeg")
        _sub(item, f"{{{ITUNES_NS}}}duration", str(e.duration_s))
    ET.indent(rss)
    body = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def upsert_episode(episodes: list[Episode], new: Episode) -> list[Episode]:
    """Return a new list: ``new`` replaces any episode of the same day, newest first, max 60."""
    merged = [e for e in episodes if e.day != new.day] + [new]
    merged.sort(key=lambda e: e.day, reverse=True)
    return merged[:MAX_EPISODES]
