import hashlib
from datetime import datetime, timezone
from pathlib import Path

from radio.sources import fetch_stories

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
