from datetime import date, datetime
from types import SimpleNamespace

import pytest

from radio.models import Story
from radio.script import ScriptGroundingError, select_and_write, unsupported_numbers


def story(id="a", title="OpenAI invierte", summary="Invertirá 8 mil millones", body=None):
    return Story(id=id, title=title, url="http://x/" + id, source="Fuente",
                 published=datetime(2026, 11, 9), summary=summary, body=body)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(text=self.replies.pop(0))])


def reply(body, used="a"):
    return f"TITULO: Titulo del dia\nUSADAS: {used}\n\n{body}"


def test_unsupported_numbers_flags_invented_figure():
    s = story(summary="<p>Invertirá 8 mil millones</p>")
    assert unsupported_numbers("Invertirá 12 mil millones de dólares.", [s]) == ["12"]


def test_supported_numbers_pass():
    s = story(summary="<p>Invertirá 8 mil millones</p>", body="Crece un 3,5% al año")
    assert unsupported_numbers("Son 8 mil millones y un 3,5% anual.", [s]) == []


def test_select_and_write_retries_once_when_unsupported_numbers():
    client = FakeClient([reply("Invertirá 12 mil millones."), reply("Invertirá 8 mil millones.")])
    res = select_and_write([story()], date(2026, 11, 10), [], client)
    assert len(client.prompts) == 2
    assert res.text == "Invertirá 8 mil millones."
    assert res.title == "Titulo del dia"
    assert [s.id for s in res.used] == ["a"]


def test_raises_when_second_attempt_also_unsupported():
    client = FakeClient([reply("Son 12 mil."), reply("Son 99 mil.")])
    with pytest.raises(ScriptGroundingError):
        select_and_write([story()], date(2026, 11, 10), [], client)
    assert len(client.prompts) == 2


def test_corrections_included_in_prompt():
    client = FakeClient([reply("Texto limpio.")])
    select_and_write([story()], date(2026, 11, 10), ["Ayer dijimos mal X"], client)
    assert "Ayer dijimos mal X" in client.prompts[0]


def test_body_none_story_presented_with_summary_only_and_unknown_ids_ignored():
    client = FakeClient([reply("Texto.", used="a,zzz")])
    res = select_and_write([story(summary="<b>Resumen</b>")], date(2026, 11, 10), [], client)
    assert [s.id for s in res.used] == ["a"]
    assert "<b>" not in client.prompts[0]
    assert "no afirmes" in client.prompts[0].lower()
