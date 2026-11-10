from datetime import date, datetime
from types import SimpleNamespace

import pytest

from radio.models import Story
from radio.script import ScriptGroundingError, ScriptTruncatedError, select_and_write, unsupported_numbers


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


def test_decimal_source_does_not_allow_joined_digits():
    s = story(summary="Crece 1,2 millones")
    assert unsupported_numbers("Son 12 millones", [s]) == ["12"]


def test_thousands_and_decimal_equivalence():
    assert unsupported_numbers("Son 1.200", [story(summary="1,200 casos")]) == []
    assert unsupported_numbers("Son 1,200", [story(summary="1.200 casos")]) == []
    assert unsupported_numbers("Sube 1,5", [story(summary="sube 1.5")]) == []
    assert unsupported_numbers("Sube 1.5", [story(summary="sube 1,5")]) == []


def test_correction_figures_are_allowed():
    client = FakeClient([reply("Ayer dijimos 12 pero eran 8.")])
    res = select_and_write([story(summary="Invertirá 8")], date(2026, 11, 10),
                           ["dijimos 12, eran 8"], client)
    assert len(client.prompts) == 1 and res.text


def test_spoken_date_in_prompt_and_allowed():
    client = FakeClient([reply("Hoy es 10 de noviembre de 2026.")])
    select_and_write([story()], date(2026, 11, 10), [], client)
    assert "10 de noviembre de 2026" in client.prompts[0]
    assert len(client.prompts) == 1


def test_fenced_and_bold_headers_parsed():
    raw = "```\n**TITULO:** Mi titulo\n**USADAS:** a, zzz\n\nCuerpo limpio.\n```"
    client = FakeClient([raw])
    res = select_and_write([story()], date(2026, 11, 10), [], client)
    assert res.title == "Mi titulo" and [s.id for s in res.used] == ["a"]
    assert res.text == "Cuerpo limpio."


def test_missing_headers_retry_then_fail():
    client = FakeClient(["Solo guion.", "Solo guion otra vez."])
    with pytest.raises(ScriptGroundingError):
        select_and_write([story()], date(2026, 11, 10), [], client)
    assert len(client.prompts) == 2 and "TITULO" in client.prompts[1]


def test_missing_headers_then_good_retry():
    client = FakeClient(["Solo guion.", reply("Bien.")])
    res = select_and_write([story()], date(2026, 11, 10), [], client)
    assert res.text == "Bien."


def test_used_ids_not_digit_checked():
    client = FakeClient([reply("Texto.", used="a")])
    res = select_and_write([story(id="a")], date(2026, 11, 10), [], client)
    assert len(client.prompts) == 1 and res.used


def test_truncated_raises():
    client = FakeClient([reply("x")])
    orig = client._create
    def create(**kw):
        r = orig(**kw); r.stop_reason = "max_tokens"; return r
    client.messages = SimpleNamespace(create=create)
    with pytest.raises(ScriptTruncatedError):
        select_and_write([story()], date(2026, 11, 10), [], client)


def test_response_without_text_block_retries():
    calls = []
    def create(**kw):
        calls.append(1)
        if len(calls) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="thinking")])
        return SimpleNamespace(content=[SimpleNamespace(text=reply("Bien."))])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    assert select_and_write([story()], date(2026, 11, 10), [], client).text == "Bien."
    assert len(calls) == 2
