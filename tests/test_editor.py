import json
from datetime import date

import pytest

from radio.archive import ArchivedStory, DayRecord
from radio.llm import LlmReply
from radio.video.director import Briefing, Thread
from radio.video.editor import EditorError, write_scenes
from radio.video.scenes import SceneScript


def week():
    st = ArchivedStory(id="a", title="Titular a", url="http://x/a", source="Bloomberg",
                       summary="Resumen", body="Hubo 11 días de espera.")
    return [DayRecord(date(2026, 11, 9), "Lunes", "Guion lunes con 42 millones.", [st])]


def briefing():
    return Briefing("Tesis", [Thread("Hilo", "ángulo", ["a"], ["11 días"], True),
                              Thread("Dos", "x", ["a"], [], False),
                              Thread("Tres", "y", ["a"], [], False)])


def scene(i, kind="titular", narration=None, **kw):
    d = {"id": f"s{i}", "kind": kind, "narration": narration or " ".join(["palabra"] * 60),
         "on_screen": "Texto", "value": None, "chart": None, "timeline": None,
         "source": None, "short": i == 1}
    d.update(kw)
    return d


def good(first_narration=None):
    sc = [scene(1, narration=first_narration)] + [scene(i) for i in range(2, 7)] + \
         [scene(7, "cierre")]
    return json.dumps({"title": "Titulo", "thesis": "Tesis", "scenes": sc})


class FakeLlm:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, prompt, *, model, max_tokens):
        self.prompts.append(prompt)
        return LlmReply(text=self.replies.pop(0), stop="end")


def test_write_scenes_returns_valid_script():
    s = write_scenes(briefing(), week(), FakeLlm(good()), "m")
    assert isinstance(s, SceneScript) and len(s.scenes) == 7


def test_prompt_contains_briefing_stories_and_daily_scripts():
    llm = FakeLlm(good())
    write_scenes(briefing(), week(), llm, "m")
    p = llm.prompts[0]
    assert "Tesis" in p and '<fuente id="a">' in p and "Guion lunes con 42 millones." in p


def test_invented_number_retries_with_feedback():
    llm = FakeLlm(good("Subió 999 por ciento."), good())
    write_scenes(briefing(), week(), llm, "m")
    assert "999" in llm.prompts[1]


def test_invented_number_twice_raises_editor_error():
    bad = good("Subió 999 por ciento.")
    with pytest.raises(EditorError, match="999"):
        write_scenes(briefing(), week(), FakeLlm(bad, bad), "m")


def test_scene_error_retries_once():
    llm = FakeLlm("no es json", good())
    write_scenes(briefing(), week(), llm, "m")
    assert "JSON" in llm.prompts[1]


def test_scene_error_twice_raises_editor_error():
    with pytest.raises(EditorError):
        write_scenes(briefing(), week(), FakeLlm("x", "y"), "m")


def test_figure_from_daily_script_is_allowed():
    s = write_scenes(briefing(), week(), FakeLlm(good("Se movieron 42 millones.")), "m")
    assert "42" in s.scenes[0].narration


def test_figure_from_story_body_is_allowed():
    write_scenes(briefing(), week(), FakeLlm(good("Fueron 11 días.")), "m")
