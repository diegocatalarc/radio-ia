import hashlib
from datetime import datetime, timezone
from pathlib import Path

import dataclasses

from radio.models import Story
from radio.sources import FeedStats, balance_pool, collect_pool, fetch_bodies, fetch_stories

FEED_URL = "https://example.com/feed.xml"
FIXTURE = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()
ARTICLE_HTML = (
    "<html><body><article><p>"
    + "La inteligencia artificial está transformando la economía global. " * 20
    + "</p></article></body></html>"
)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


SINCE = datetime(2026, 11, 1, tzinfo=timezone.utc)


def test_fetch_stories_filters_by_date():
    client = FakeClient({FEED_URL: FIXTURE, "https://example.com/a1": ARTICLE_HTML,
                         "https://example.com/a2": ARTICLE_HTML})
    stories = fetch_stories([FEED_URL], SINCE, client=client)
    assert len(stories) == 2
    assert {s.url for s in stories} == {"https://example.com/a1", "https://example.com/a2"}
    expected = hashlib.sha256(b"https://example.com/a1").hexdigest()[:16]
    assert {s.id for s in stories if s.url.endswith("a1")} == {expected}
    again = fetch_stories([FEED_URL], SINCE, client=client)
    assert {s.id for s in again} == {s.id for s in stories}
    assert stories[0].body and "inteligencia artificial" in stories[0].body


def test_story_without_extractable_body_has_none_body():
    client = FakeClient({FEED_URL: FIXTURE, "https://example.com/a1": "",
                         "https://example.com/a2": "<html><body></body></html>"})
    stories = fetch_stories([FEED_URL], SINCE, client=client)
    assert len(stories) == 2
    assert all(s.body is None for s in stories)
    assert {s.summary for s in stories} == {"Resumen uno", "Resumen dos"}


def test_failing_feed_does_not_stop_others():
    client = FakeClient({"https://bad.example/feed": RuntimeError("down"),
                         FEED_URL: FIXTURE,
                         "https://example.com/a1": ARTICLE_HTML,
                         "https://example.com/a2": RuntimeError("paywall")})
    stories = fetch_stories(["https://bad.example/feed", FEED_URL], SINCE, client=client)
    assert len(stories) == 2
    bodies = {s.url: s.body for s in stories}
    assert bodies["https://example.com/a2"] is None


def test_bad_entry_does_not_abort_rest_of_feed(monkeypatch):
    import radio.sources as sources

    real = sources.story_id

    def flaky(url):
        if url.endswith("a1"):
            raise ValueError("boom")
        return real(url)

    monkeypatch.setattr(sources, "story_id", flaky)
    client = FakeClient({FEED_URL: FIXTURE, "https://example.com/a1": ARTICLE_HTML,
                         "https://example.com/a2": ARTICLE_HTML})
    stories = fetch_stories([FEED_URL], SINCE, client=client)
    assert [s.url for s in stories] == ["https://example.com/a2"]


def test_malformed_feed_logs_warning_and_keeps_others(caplog):
    bad = "https://bad.example/feed"
    client = FakeClient({bad: "this is not xml at all", FEED_URL: FIXTURE,
                         "https://example.com/a1": ARTICLE_HTML,
                         "https://example.com/a2": ARTICLE_HTML})
    with caplog.at_level("WARNING", logger="radio.sources"):
        stories = fetch_stories([bad, FEED_URL], SINCE, client=client)
    assert len(stories) == 2
    assert any(bad in r.getMessage() for r in caplog.records)


EMPTY_FEED = "<rss version='2.0'><channel><title>vacio</title></channel></rss>"


def test_collect_pool_makes_no_article_requests_and_has_no_bodies():
    client = FakeClient({FEED_URL: FIXTURE})
    pool, stats = collect_pool([FEED_URL], SINCE, client=client)
    assert client.requested == [FEED_URL]
    assert len(pool) == 2 and all(s.body is None for s in pool)
    assert stats == FeedStats(total=1, failed=0, failed_urls=[])


def test_feed_stats_count_errored_malformed_and_empty_feeds():
    client = FakeClient({"https://err.example/f": RuntimeError("down"),
                         "https://bad.example/f": "not xml at all",
                         "https://empty.example/f": EMPTY_FEED,
                         FEED_URL: FIXTURE})
    pool, stats = collect_pool(["https://err.example/f", "https://bad.example/f",
                                "https://empty.example/f", FEED_URL], SINCE, client=client)
    assert len(pool) == 2
    assert stats.total == 4 and stats.failed == 3
    assert "https://err.example/f" in stats.failed_urls


def test_feed_with_only_old_entries_is_not_a_failure():
    old = FIXTURE.replace("Mon, 09 Nov 2026", "Mon, 01 Jan 2024")
    pool, stats = collect_pool([FEED_URL], SINCE, client=FakeClient({FEED_URL: old}))
    assert pool == [] and stats.failed == 0


def _st(i, source, hours):
    from datetime import timedelta
    return Story(id=f"{source}{i}", title="t", url=f"http://x/{source}{i}", source=source,
                 published=datetime(2026, 11, 10, tzinfo=timezone.utc) - timedelta(hours=hours),
                 summary="")


def test_balance_pool_round_robin_so_noisy_feed_cannot_take_all_slots():
    noisy = [_st(i, "N", i) for i in range(20)]       # newest overall
    quiet = [_st(i, "Q", 30 + i) for i in range(3)]
    pool = balance_pool(noisy + quiet, 8)
    assert len(pool) == 8
    assert sum(s.source == "Q" for s in pool) == 3
    assert [s.published for s in pool] == sorted((s.published for s in pool), reverse=True)
    assert len(balance_pool(noisy, 100)) == 20


LONG = "Texto del articulo sobre inteligencia artificial y economia. " * 30


def _html(text):
    return f"<html><body><article><p>{text}</p></article></body></html>"


def _story(url="https://example.com/a1"):
    return Story(id="1", title="t", url=url, source="s",
                 published=datetime(2026, 11, 9, tzinfo=timezone.utc), summary="r")


def test_fetch_bodies_extracts_and_caps_at_8000():
    huge = "Texto del articulo sobre inteligencia artificial y economia. " * 400
    out = fetch_bodies([_story()], client=FakeClient({"https://example.com/a1": _html(huge)}))
    assert out[0].body and 500 <= len(out[0].body) <= 8000
    assert out[0].id == "1" and out[0].summary == "r"


def test_fetch_bodies_short_body_is_none():
    out = fetch_bodies([_story()], client=FakeClient(
        {"https://example.com/a1": _html("Muy corto, no sirve.")}))
    assert out[0].body is None


def test_fetch_bodies_bot_wall_is_none():
    for phrase in ["Please enable JavaScript", "Verify you are human", "Complete the CAPTCHA",
                   "Subscribe to continue", "Suscríbete para seguir leyendo"]:
        page = _html(LONG + phrase)
        out = fetch_bodies([_story()], client=FakeClient({"https://example.com/a1": page}))
        assert out[0].body is None, phrase


def test_fetch_bodies_error_is_none_and_input_not_mutated():
    s = _story()
    out = fetch_bodies([s], client=FakeClient({"https://example.com/a1": RuntimeError("x")}))
    assert out[0].body is None and s.body is None
    assert dataclasses.is_dataclass(out[0])
