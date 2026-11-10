import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_feeds", Path(__file__).parent.parent / "scripts" / "check_feeds.py")
check_feeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_feeds)

FIXTURE = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()
LONG = "<html><body><article><p>" + "Texto sobre economia e IA. " * 40 + "</p></article></body></html>"


class Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class Client:
    def get(self, url, **kw):
        if "bad" in url:
            raise RuntimeError("down")
        return Resp(FIXTURE if url.endswith("feed.xml") else LONG)


def test_check_feed_reports_counts_and_body_length():
    since = datetime(2026, 11, 1, tzinfo=timezone.utc)
    ok, report = check_feeds.check_feed(Client(), "https://x/feed.xml", since)
    assert ok and "entradas: 3" in report and "36 h: 2" in report
    assert report.count("cuerpo ") == 2 and "caracteres" in report


def test_check_feed_reports_error():
    ok, report = check_feeds.check_feed(Client(), "https://bad/feed", datetime.now(timezone.utc))
    assert not ok and report.startswith("error")
