import json
from datetime import date

import pytest

from radio.archive import ArchivedStory, DayRecord
from radio.llm import LlmReply
from radio.video.director import Briefing, DirectorError, direct


def week():
    def st(i, summ="Resumen"):
        return ArchivedStory(id=i, title=f"Titular {i}", url=f"http://x/{i}", source="Bloomberg",
                             summary=summ, body="Hubo 11 días de espera.")
    return [DayRecord(date(2026, 11, 9), "Lunes", "Guion lunes.", [st("a"), st("b")]),
            DayRecord(date(2026, 11, 10), "Martes", "Guion martes.", [st("c"), st("d")])]


def thread(ids, short=False, figures=(), title="Hilo"):
    return {"title": title, "angle": "ángulo", "story_ids": [ids] if isinstance(ids, str) else list(ids),
            "figures": list(figures), "short": short}


def good(**kw):
    d = {"thesis": "Tesis", "threads": [thread("a", True, ["11 días"]), thread("b"), thread("c")]}
    d.update(kw)
    return json.dumps(d)


class FakeLlm:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, prompt, *, model, max_tokens):
        self.prompts.append(prompt)
        return LlmReply(text=self.replies.pop(0), stop="end")


def test_direct_returns_briefing():
    b = direct(week(), FakeLlm(good()), "m")
    assert isinstance(b, Briefing) and b.thesis == "Tesis" and len(b.threads) == 3
    assert b.threads[0].short and b.threads[0].figures == ["11 días"]


def test_direct_accepts_json_fence():
    assert len(direct(week(), FakeLlm("```json\n" + good() + "\n```"), "m").threads) == 3


def test_unknown_story_id_retries_then_succeeds():
    bad = good(threads=[thread("zzz", True), thread("b"), thread("c")])
    llm = FakeLlm(bad, good())
    assert len(direct(week(), llm, "m").threads) == 3
    assert "zzz" in llm.prompts[1]


def test_unknown_story_id_twice_raises():
    bad = good(threads=[thread("zzz", True), thread("b"), thread("c")])
    with pytest.raises(DirectorError, match="zzz"):
        direct(week(), FakeLlm(bad, bad), "m")


def test_no_short_thread_rejected():
    bad = good(threads=[thread("a"), thread("b"), thread("c")])
    with pytest.raises(DirectorError, match="short"):
        direct(week(), FakeLlm(bad, bad), "m")


def test_unsupported_figure_rejected():
    bad = good(threads=[thread("a", True, ["500 millones"]), thread("b"), thread("c")])
    with pytest.raises(DirectorError, match="500"):
        direct(week(), FakeLlm(bad, bad), "m")


def test_two_threads_rejected():
    bad = good(threads=[thread("a", True), thread("b")])
    with pytest.raises(DirectorError, match="hilos"):
        direct(week(), FakeLlm(bad, bad), "m")


def test_invalid_json_rejected():
    with pytest.raises(DirectorError, match="JSON"):
        direct(week(), FakeLlm("nada", "nada"), "m")


def test_prompt_wraps_stories_in_fuente_tags_and_includes_scripts():
    llm = FakeLlm(good())
    direct(week(), llm, "m")
    p = llm.prompts[0]
    assert '<fuente id="a">' in p and "Titular a" in p and "Guion lunes." in p
    assert "2026-11-09" in p


def test_story_in_two_threads_rejected():
    bad = good(threads=[thread("a", True), thread("a"), thread("c")])
    with pytest.raises(DirectorError, match="más de un hilo"):
        direct(week(), FakeLlm(bad, bad), "m")


def test_arc_is_parsed_and_optional():
    t = thread("a", True)
    t["arc"] = "lunes: renuncia; jueves: regreso"
    b = direct(week(), FakeLlm(good(threads=[t, thread("b"), thread("c")])), "m")
    assert b.threads[0].arc == "lunes: renuncia; jueves: regreso" and b.threads[1].arc == ""


def test_prompt_demands_multi_day_stories_told_once_and_lists_previous_weeks():
    prev = [{"label": "2–8 de noviembre de 2026", "title": "Semana vieja",
             "thesis": "Tesis vieja de la semana"}]
    llm = FakeLlm(good())
    direct(week(), llm, "m", previous=prev)
    p = llm.prompts[0]
    assert "UNA sola vez" in p and "SEMANAS ANTERIORES" in p
    assert "Tesis vieja de la semana" in p and "Semana vieja" in p and "2–8 de noviembre" in p


def test_prompt_without_previous_weeks_says_none():
    llm = FakeLlm(good())
    direct(week(), llm, "m")
    assert "(ninguna)" in llm.prompts[0]
