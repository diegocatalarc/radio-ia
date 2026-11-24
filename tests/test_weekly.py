import json
from datetime import date, datetime, timezone

import pytest

from radio.archive import ArchivedStory, DayRecord, save_day
from radio.config import Config
from radio.llm import LlmReply
from radio.video.voice import VoiceError
from radio.weekly import WeeklyDeps, run_weekly, week_id

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)  # domingo 07:00 en Santiago


def seed(site, days=(10, 11, 12, 13, 14, 15)):
    for d in days:
        st = ArchivedStory(id=f"s{d}", title=f"Titular {d}", url=f"http://x/{d}", source="Bloomberg",
                           summary="Resumen", body="Cuerpo")
        save_day(site, DayRecord(date(2026, 11, d), f"Dia {d}", f"Guion {d}.", [st]))


def director_reply(days):
    ids = [f"s{d}" for d in days]
    th = [{"title": f"H{i}", "angle": "a", "story_ids": [ids[i]], "figures": [], "short": i == 0}
          for i in range(3)]
    return json.dumps({"thesis": "Tesis", "threads": th})


def editor_reply():
    def sc(i, kind="titular"):
        return {"id": f"s{i}", "kind": kind, "narration": " ".join(["palabra"] * 60),
                "on_screen": "Texto", "value": None, "chart": None, "timeline": None,
                "source": None, "short": i == 1}
    scenes = [sc(i) for i in range(1, 7)] + [sc(7, "cierre")]
    return json.dumps({"title": "Titulo semanal", "thesis": "Tesis", "scenes": scenes})


class FakeLlm:
    def __init__(self, days=(10, 11, 12), editor=None):
        self.days, self.editor, self.calls = days, editor, 0

    def complete(self, prompt, *, model, max_tokens):
        self.calls += 1
        text = director_reply(self.days) if "director editorial" in prompt else \
            (self.editor if self.editor is not None else editor_reply())
        return LlmReply(text=text, stop="end")


class FakeTts:
    max_chars = 4000

    def __init__(self, fail=False, empty=False):
        self.fail, self.empty = fail, empty

    def speak(self, chunk):
        if self.fail:
            raise RuntimeError("tts down")
        return b"" if self.empty else b"\xff\xfb\x90\x00" + b"\x00" * 16000


class Renderer:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def __call__(self, props_path, public_dir, composition, out_path):
        self.calls.append(composition)
        if self.fail:
            raise RuntimeError("render down")
        out_path.write_bytes(f"mp4:{composition}".encode())


def make(tmp_path, llm=None, tts=None, render=None):
    return WeeklyDeps(llm=llm or FakeLlm(), tts=tts or FakeTts(), site_dir=tmp_path / "site",
                      work_dir=tmp_path / "work", render=render or Renderer())


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def cfg():
    return Config(weekly_model="", model="m")


def test_week_id_is_iso_week():
    assert week_id(date(2026, 11, 15)) == "2026-W46"
    assert week_id(date(2026, 12, 31)) == "2026-W53"


def test_run_weekly_publishes_both_videos_and_index(tmp_path):
    d = make(tmp_path)
    seed(d.site_dir)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 0 and res.status == "published" and res.day == date(2026, 11, 15)
    idx = json.loads((d.site_dir / "weekly.json").read_text())
    assert len(idx) == 1 and idx[0]["week"] == "2026-W46" and idx[0]["title"] == "Titulo semanal"
    assert idx[0]["video_16x9"] == "weekly/2026-W46-16x9.mp4"
    assert (d.site_dir / idx[0]["video_16x9"]).read_bytes() == b"mp4:Semanal16x9"
    assert (d.site_dir / idx[0]["video_9x16"]).read_bytes() == b"mp4:Semanal9x16"
    assert d.render.calls == ["Semanal16x9", "Semanal9x16"]


def test_run_weekly_skips_with_fewer_than_4_days_exit_2(tmp_path):
    d = make(tmp_path)
    seed(d.site_dir, days=(13, 14, 15))
    before = snapshot(tmp_path)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 2 and res.status == "skipped"
    assert snapshot(tmp_path) == before and d.llm.calls == 0


def test_run_weekly_works_with_gaps_and_labels_real_dates(tmp_path):
    d = make(tmp_path, llm=FakeLlm(days=(10, 12, 14)))
    seed(d.site_dir, days=(10, 12, 14, 15))
    assert run_weekly(cfg(), NOW, d).exit_code == 0
    idx = json.loads((d.site_dir / "weekly.json").read_text())
    assert idx[0]["label"] == "10–15 de noviembre de 2026"


def test_run_weekly_is_idempotent_without_force(tmp_path):
    d = make(tmp_path)
    seed(d.site_dir)
    run_weekly(cfg(), NOW, d)
    calls, snap = d.llm.calls, snapshot(d.site_dir)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 0 and "ya existe" in res.message
    assert d.llm.calls == calls and snapshot(d.site_dir) == snap


def test_run_weekly_force_regenerates_and_replaces_entry(tmp_path):
    d = make(tmp_path)
    seed(d.site_dir)
    run_weekly(cfg(), NOW, d)
    calls = d.llm.calls
    assert run_weekly(cfg(), NOW, d, force=True).exit_code == 0
    assert d.llm.calls > calls
    assert len(json.loads((d.site_dir / "weekly.json").read_text())) == 1


def test_tts_failure_leaves_site_untouched(tmp_path):
    d = make(tmp_path, tts=FakeTts(fail=True))
    seed(d.site_dir)
    before = snapshot(d.site_dir)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 1 and "tts down" in res.message
    assert snapshot(d.site_dir) == before


def test_empty_audio_leaves_site_untouched(tmp_path):
    d = make(tmp_path, tts=FakeTts(empty=True))
    seed(d.site_dir)
    before = snapshot(d.site_dir)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 1 and VoiceError.__name__ in res.message
    assert snapshot(d.site_dir) == before


def test_render_failure_leaves_site_untouched(tmp_path):
    d = make(tmp_path, render=Renderer(fail=True))
    seed(d.site_dir)
    before = snapshot(d.site_dir)
    assert run_weekly(cfg(), NOW, d).exit_code == 1
    assert snapshot(d.site_dir) == before


def test_second_render_failure_leaves_site_untouched(tmp_path):
    class Half(Renderer):
        def __call__(self, props_path, public_dir, composition, out_path):
            if composition == "Semanal9x16":
                raise RuntimeError("render down")
            super().__call__(props_path, public_dir, composition, out_path)

    d = make(tmp_path, render=Half())
    seed(d.site_dir)
    before = snapshot(d.site_dir)
    assert run_weekly(cfg(), NOW, d).exit_code == 1
    assert snapshot(d.site_dir) == before


def test_editor_failure_exit_1_site_untouched(tmp_path):
    d = make(tmp_path, llm=FakeLlm(editor="no es json"))
    seed(d.site_dir)
    before = snapshot(d.site_dir)
    res = run_weekly(cfg(), NOW, d)
    assert res.exit_code == 1 and res.status == "failed"
    assert snapshot(d.site_dir) == before


def test_keeps_only_last_4_weeks_and_prunes_mp4(tmp_path):
    d = make(tmp_path)
    seed(d.site_dir)
    (d.site_dir / "weekly").mkdir()
    old = []
    for w in ("2026-W41", "2026-W42", "2026-W43", "2026-W44"):
        for f in ("16x9", "9x16"):
            (d.site_dir / "weekly" / f"{w}-{f}.mp4").write_bytes(b"old")
        old.append({"week": w, "label": w, "title": w, "video_16x9": f"weekly/{w}-16x9.mp4",
                    "video_9x16": f"weekly/{w}-9x16.mp4", "published": "2026-10-01T00:00:00+00:00"})
    (d.site_dir / "weekly.json").write_text(json.dumps(old))
    (d.site_dir / "weekly" / "huerfano.mp4").write_bytes(b"x")
    assert run_weekly(cfg(), NOW, d).exit_code == 0
    idx = json.loads((d.site_dir / "weekly.json").read_text())
    assert [e["week"] for e in idx] == ["2026-W46", "2026-W44", "2026-W43", "2026-W42"]
    names = sorted(p.name for p in (d.site_dir / "weekly").glob("*.mp4"))
    assert names == sorted(f"{w}-{f}.mp4" for w in ("2026-W46", "2026-W44", "2026-W43", "2026-W42")
                           for f in ("16x9", "9x16"))
