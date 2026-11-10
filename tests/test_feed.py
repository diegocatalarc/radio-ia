import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from radio.feed import Episode, build_feed, upsert_episode

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def ep(day, title="Hola", **kw):
    d = dict(day=day, title=title, description="desc", mp3_path=f"docs/episodes/{day.isoformat()}.mp3",
             duration_s=600, size_bytes=1234)
    d.update(kw)
    return Episode(**d)


def test_empty_feed_is_valid_rss():
    xml = build_feed([], "https://x.github.io/radio/", "America/Santiago")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(xml.encode("utf-8"))
    ch = root.find("channel")
    assert root.tag == "rss" and root.get("version") == "2.0"
    assert ch.findtext("language") == "es"
    assert ch.findtext(ITUNES + "explicit") == "false"
    assert ch.findtext("title") and ch.findtext("description") and ch.findtext("link")
    assert ch.findtext(ITUNES + "author")
    assert ch.findall("item") == []


def test_title_with_ampersand_and_accents_is_escaped():
    e = ep(date(2026, 11, 10), title='IA & Economía <1> "ñandú"')
    xml = build_feed([e], "https://x.github.io/radio", "America/Santiago")
    item = ET.fromstring(xml.encode("utf-8")).find("channel/item")
    assert item.findtext("title") == 'IA & Economía <1> "ñandú"'
    enc = item.find("enclosure")
    assert enc.get("url") == "https://x.github.io/radio/episodes/2026-11-10.mp3"
    assert enc.get("length") == "1234" and enc.get("type") == "audio/mpeg"
    guid = item.find("guid")
    assert guid.text == "2026-11-10" and guid.get("isPermaLink") == "false"
    assert item.findtext(ITUNES + "duration") == "600"
    assert item.findtext("pubDate") == "Tue, 10 Nov 2026 02:00:00 -0300"


def test_upsert_replaces_same_day_episode():
    d = date(2026, 11, 10)
    original = [ep(d, "viejo"), ep(d - timedelta(days=1), "ayer")]
    out = upsert_episode(original, ep(d, "nuevo"))
    assert [e.title for e in out] == ["nuevo", "ayer"]
    assert original[0].title == "viejo" and len(original) == 2


def test_upsert_keeps_latest_60():
    d = date(2026, 1, 1)
    eps = []
    for i in range(70):
        eps = upsert_episode(eps, ep(d + timedelta(days=i)))
    assert len(eps) == 60
    assert eps[0].day == d + timedelta(days=69)
    assert eps[-1].day == d + timedelta(days=10)


def test_published_used_verbatim_regardless_of_tz():
    pub = datetime(2026, 11, 10, 2, 5, 9, tzinfo=timezone(timedelta(hours=-3)))
    xml = build_feed([ep(date(2026, 11, 10), published=pub)], "https://x", "Asia/Tokyo")
    item = ET.fromstring(xml.encode("utf-8")).find("channel/item")
    assert item.findtext("pubDate") == "Tue, 10 Nov 2026 02:05:09 -0300"


def test_fallback_uses_custom_publish_hour():
    xml = build_feed([ep(date(2026, 11, 10))], "https://x", "America/Santiago", publish_hour=7)
    item = ET.fromstring(xml.encode("utf-8")).find("channel/item")
    assert item.findtext("pubDate") == "Tue, 10 Nov 2026 07:00:00 -0300"


def test_control_chars_are_stripped():
    xml = build_feed([ep(date(2026, 11, 10), title="a\x0bb\x00c")], "https://x", "UTC")
    item = ET.fromstring(xml.encode("utf-8")).find("channel/item")
    assert item.findtext("title") == "abc"
