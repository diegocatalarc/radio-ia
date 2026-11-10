import json
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from radio.config import Config
from radio.llm import LlmReply
from radio.feed import Episode
import pytest

from radio.run import Deps, estimate_mp3_duration_s, main, run
from radio.state import State

SANTIAGO = ZoneInfo("America/Santiago")
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)  # 07:00 in Santiago (UTC-3 in Nov)


def make_feed_xml(stories):
    items = "".join(
        f"<item><title>{t}</title><link>http://x/{i}-{t}</link><description>Resumen {i}</description>"
        f"<pubDate>Fri, 01 Jan 2027 00:00:00 GMT</pubDate></item>"
        for i, t in stories)
    return f"<rss version='2.0'><channel><title>f</title>{items}</channel></rss>"


class FakeHttp:
    def __init__(self, n, bad=()):
        self.xml = make_feed_xml([(f"s{i}", f"Historia {i}") for i in range(n)])
        self.bad = set(bad)
        self.requested = []

    def get(self, url, **kw):
        self.requested.append(url)
        if url in self.bad:
            raise RuntimeError("feed down")
        resp = SimpleNamespace(text=self.xml, status_code=200)
        resp.raise_for_status = lambda: None
        return resp


class FakeClaude:
    def __init__(self, n_used=None):
        self.n_used = n_used
        self.pick = lambda ids: ids[:2] + ids[-1:]
        self.calls = []

    def complete(self, prompt, *, model, max_tokens):
        self.calls.append(prompt)
        ids = [f"{i}" for i in range(0, 0)]
        import re
        ids = re.findall(r"\[id: ([^\]]+)\]", prompt)
        if "ELEGIDAS" in prompt:  # llamada de selección
            self.pool_ids = ids
            return LlmReply(text="ELEGIDAS: " + ",".join(self.pick(ids)), stop="end")
        if self.n_used:
            ids = ids[:self.n_used]
        return LlmReply(
            text=f"TITULO: Titulo del dia\nUSADAS: {','.join(ids)}\n\nHola oyentes.", stop="end")


class FakeTts:
    max_chars = 4000

    def __init__(self, fail=False):
        self.fail = fail

    def speak(self, chunk):
        if self.fail:
            raise RuntimeError("tts down")
        return b"\xff\xfb\x90\x00" + b"\x00" * 16000


def cfg(**kw):
    base = dict(feeds=["http://feed/1"], site_url="https://example.org/radio", max_stories=6)
    base.update(kw)
    return Config(**base)


def deps(tmp_path, n=4, tts=None, claude=None, bad=()):
    return Deps(claude=claude or FakeClaude(), tts=tts or FakeTts(), http=FakeHttp(n, bad),
                site_dir=tmp_path / "site", state_path=tmp_path / "state.json")


def snapshot(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*")) if p.is_file()}


def test_publishes_episode_and_updates_feed(tmp_path):
    d = deps(tmp_path)
    res = run(cfg(), NOW, d)
    assert res.exit_code == 0 and res.status == "published"
    assert res.day == date(2026, 11, 10)
    mp3 = d.site_dir / "episodes" / "episodio-2026-11-10.mp3"
    assert mp3.read_bytes().startswith(b"\xff\xfb")
    eps = json.loads((d.site_dir / "episodes.json").read_text())
    assert eps[0]["day"] == "2026-11-10" and eps[0]["duration_s"] > 0
    assert eps[0]["published"].endswith("-03:00")
    feed = (d.site_dir / "feed.xml").read_text()
    assert feed.count("<item>") == 1 and "episodio-2026-11-10.mp3" in feed
    st = json.loads(d.state_path.read_text())
    assert len(st["used"]) == 4 and set(st["used"].values()) == {"2026-11-10"}


def test_fewer_than_two_stories_publishes_nothing_exit_2(tmp_path):
    d = deps(tmp_path, n=1)
    res = run(cfg(), NOW, d)
    assert res.exit_code == 2 and res.status == "skipped"
    assert not d.site_dir.exists() and not d.state_path.exists()
    assert d.claude.calls == []


def test_two_or_three_stories_publishes_short_episode(tmp_path):
    for n in (2, 3):
        t = tmp_path / str(n)
        res = run(cfg(), NOW, deps(t, n=n))
        assert res.exit_code == 0 and res.stories == n


def test_story_count_is_new_fetched_stories_before_writing(tmp_path):
    # 5 fetched, but the model only uses 1: still published (count is pre-writing).
    d = deps(tmp_path, n=5, claude=FakeClaude(n_used=1))
    res = run(cfg(), NOW, d)
    assert res.exit_code == 0 and res.stories == 1


def test_failure_midway_leaves_existing_files_untouched(tmp_path):
    good = deps(tmp_path)
    assert run(cfg(), NOW, good).exit_code == 0
    State.load(good.state_path)
    s = State.load(good.state_path)
    s.add_correction("corregir X")
    s.save(good.state_path)
    before = snapshot(tmp_path)
    bad = deps(tmp_path, tts=FakeTts(fail=True))
    bad.http.xml = make_feed_xml([(f"n{i}", f"Nueva {i}") for i in range(3)])
    res = run(cfg(), NOW + timedelta(days=1), bad)
    assert res.exit_code == 1 and res.status == "failed"
    assert snapshot(tmp_path) == before


def test_grounding_error_leaves_files_untouched(tmp_path):
    class Bad(FakeClaude):
        def complete(self, prompt, *, model, max_tokens):
            return LlmReply(text="TITULO: t\nUSADAS: 0\n\nCifra 987654.", stop="end")
    d = deps(tmp_path, claude=Bad())
    res = run(cfg(), NOW, d)
    assert res.exit_code == 1
    assert not d.site_dir.exists() and not d.state_path.exists()


def test_episode_date_uses_configured_timezone(tmp_path):
    # 2026-11-10 02:30 UTC is still Nov 9 in Santiago (UTC-3).
    early = datetime(2026, 11, 10, 2, 30, tzinfo=timezone.utc)
    d = deps(tmp_path / "a")
    assert run(cfg(), early, d).day == date(2026, 11, 9)
    assert (d.site_dir / "episodes" / "episodio-2026-11-09.mp3").exists()
    # 2026-11-10 23:30 in Santiago is already Nov 11 UTC; a UTC-time that is "tomorrow" in Tokyo.
    late = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)  # Nov 11 01:00 in Tokyo
    d2 = deps(tmp_path / "b")
    res = run(cfg(timezone="Asia/Tokyo"), late, d2)
    assert res.day == date(2026, 11, 11)
    st = json.loads(d2.state_path.read_text())
    assert set(st["used"].values()) == {"2026-11-11"}
    eps = json.loads((d2.site_dir / "episodes.json").read_text())
    assert eps[0]["published"].endswith("+09:00")


def test_rerun_same_day_replaces_episode(tmp_path):
    d = deps(tmp_path)
    assert run(cfg(), NOW, d).exit_code == 0
    assert run(cfg(), NOW + timedelta(hours=1), d).exit_code == 0
    assert len(list((d.site_dir / "episodes").glob("*.mp3"))) == 1
    assert (d.site_dir / "feed.xml").read_text().count("<item>") == 1
    assert len(json.loads((d.site_dir / "episodes.json").read_text())) == 1


def test_second_day_keeps_history_and_consumes_corrections(tmp_path):
    d = deps(tmp_path)
    run(cfg(), NOW, d)
    s = State.load(d.state_path)
    s.add_correction("corregir X")
    s.save(d.state_path)
    d2 = deps(tmp_path, claude=FakeClaude())
    d2.http = FakeHttp(4)
    # new day: previous stories are used, so use different ids via a new feed
    d2.http.xml = make_feed_xml([(f"n{i}", f"Nueva {i}") for i in range(3)])
    assert run(cfg(), NOW + timedelta(days=1), d2).exit_code == 0
    assert "corregir X" in d2.claude.calls[0]
    assert State.load(d.state_path).corrections == []
    assert len(json.loads((d.site_dir / "episodes.json").read_text())) == 2


def test_duration_estimate_from_cbr_header_and_fallback():
    # MPEG1 Layer III, 128 kbps, 44.1 kHz: 16000 bytes/s
    frame = b"\xff\xfb\x90\x00"
    assert estimate_mp3_duration_s(frame + b"\x00" * (16000 * 10 - 4)) == 10
    assert estimate_mp3_duration_s(b"junk") >= 1


def test_selection_stage_chooses_from_big_pool_and_only_chosen_reach_script(tmp_path):
    d = deps(tmp_path, n=12)
    res = run(cfg(), NOW, d)
    assert res.exit_code == 0
    assert "ELEGIDAS" in d.claude.calls[0] and "ELEGIDAS" not in d.claude.calls[1]
    assert len(d.claude.pool_ids) == 12  # el pool completo (<= pool_size) llega a la selección
    script_prompt = d.claude.calls[1]
    assert script_prompt.count("[id: ") == 3
    # solo se descargan cuerpos de las elegidas (3), no de las 12
    article_gets = [u for u in d.http.requested if u.startswith("http://x/")]
    assert len(article_gets) == 3


def test_pool_size_caps_what_claude_sees(tmp_path):
    d = deps(tmp_path, n=12)
    res = run(cfg(pool_size=7, max_stories=6), NOW, d)
    assert res.exit_code == 0, res.message
    assert len(d.claude.pool_ids) == 7


def test_fewer_than_two_selected_stories_exit_2(tmp_path):
    d = deps(tmp_path, n=1)
    assert run(cfg(), NOW, d).exit_code == 2


def test_more_than_half_feeds_failed_logs_error_and_message(tmp_path, caplog):
    feeds = ["http://f/1", "http://f/2", "http://f/3"]
    d = deps(tmp_path, n=4, bad={"http://f/2", "http://f/3"})
    with caplog.at_level(logging.INFO):
        res = run(cfg(feeds=feeds), NOW, d)
    assert res.exit_code == 0  # la semántica de códigos no cambia
    assert "2 de 3 feeds" in res.message
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("2 de 3 feeds" in r.getMessage() for r in errors)


def test_half_or_fewer_failed_feeds_is_not_an_error(tmp_path, caplog):
    d = deps(tmp_path, n=4, bad={"http://f/2"})
    with caplog.at_level(logging.INFO):
        res = run(cfg(feeds=["http://f/1", "http://f/2"]), NOW, d)
    assert "feeds" not in res.message
    assert not [r for r in caplog.records
                if r.levelno == logging.ERROR and r.name.startswith("radio")]


def test_skipped_run_with_failed_feeds_reports_them(tmp_path):
    d = deps(tmp_path, n=0, bad={"http://f/2", "http://f/3"})
    res = run(cfg(feeds=["http://f/1", "http://f/2", "http://f/3"]), NOW, d)
    assert res.exit_code == 2 and "3 de 3 feeds" in res.message


def test_main_logs_missing_key_variable_name(monkeypatch, caplog):
    monkeypatch.setattr("radio.run.load_config", lambda: cfg(site_url="https://u.github.io/r"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with caplog.at_level(logging.ERROR):
        assert main() == 1
    assert any("OPENROUTER_API_KEY" in r.getMessage() for r in caplog.records)


def test_main_rejects_placeholder_site_url(monkeypatch, caplog):
    monkeypatch.setattr("radio.run.load_config", lambda: cfg())  # example.org
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with caplog.at_level(logging.ERROR):
        assert main() == 1
    assert any("config.toml" in r.getMessage() for r in caplog.records)
