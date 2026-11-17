from datetime import date, datetime, timezone

import pytest

from radio.article import ArticleError, is_trusted, trusted_candidates, write_article
from radio.llm import LlmReply
from radio.models import Story

DAY = date(2026, 11, 17)
DOMAINS = ["bloomberg.com", "theguardian.com"]
BODY = "Nvidia vendió chips por 30 mil millones. " * 30


def story(i, url, body=BODY):
    return Story(id=f"s{i}", title=f"Titular {i}", url=url, source=f"Medio {i}",
                 published=datetime(2026, 11, 16, tzinfo=timezone.utc),
                 summary="Resumen", body=body)


class FakeLlm:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.prompts = []

    def complete(self, prompt, *, model, max_tokens):
        self.prompts.append(prompt)
        return LlmReply(text=self.texts.pop(0), stop="end")


def reply(main="s0", sources="s0", body="Según Bloomberg, Nvidia vendió chips por 30 mil millones."):
    return (f"TITULO: Nvidia y el negocio de los chips\nPRINCIPAL: {main}\nFUENTES: {sources}\n"
            f"ENTRADILLA: Las ventas siguen creciendo.\n\n{body}\n\nNuestra lectura es que sigue.")


@pytest.mark.parametrize("url,ok", [
    ("https://www.bloomberg.com/news/x", True),
    ("https://bloomberg.com/x", True),
    ("https://feeds.bloomberg.com/x", True),
    ("https://notbloomberg.com/x", False),
    ("https://bloomberg.com.evil.io/x", False),
    ("https://openai.com/news/x", False),
    ("ftp://bloomberg.com/x", False),
    ("", False),
])
def test_is_trusted(url, ok):
    assert is_trusted(url, DOMAINS) is ok


def test_candidates_require_trusted_domain_and_full_text():
    stories = [story(0, "https://www.bloomberg.com/a"),
               story(1, "https://openai.com/b"),
               story(2, "https://www.theguardian.com/c", body=None)]
    assert [s.id for s in trusted_candidates(stories, DOMAINS)] == ["s0"]


def test_writes_article_only_from_trusted_sources():
    stories = [story(0, "https://www.bloomberg.com/a"), story(1, "https://openai.com/b")]
    llm = FakeLlm(reply())
    art = write_article(stories, DAY, llm, model="m", domains=DOMAINS)
    assert "[id: s0]" in llm.prompts[0] and "[id: s1]" not in llm.prompts[0]
    assert art.title == "Nvidia y el negocio de los chips"
    assert art.main.id == "s0" and [s.id for s in art.sources] == ["s0"]
    assert len(art.paragraphs) == 2
    data = art.to_json(DAY)
    assert data["day"] == "2026-11-17"
    assert data["sources"] == [{"title": "Titular 0", "source": "Medio 0",
                                "url": "https://www.bloomberg.com/a"}]


def test_ignores_ids_outside_trusted_pool():
    stories = [story(0, "https://www.bloomberg.com/a"), story(1, "https://openai.com/b")]
    art = write_article(stories, DAY, FakeLlm(reply(sources="s0,s1")), model="m", domains=DOMAINS)
    assert [s.id for s in art.sources] == ["s0"]


def test_no_trusted_story_raises():
    with pytest.raises(ArticleError):
        write_article([story(1, "https://openai.com/b")], DAY, FakeLlm(), model="m",
                      domains=DOMAINS)


def test_unsupported_number_retries_then_fails():
    stories = [story(0, "https://www.bloomberg.com/a")]
    bad = reply(body="Vendió 999 chips.")
    llm = FakeLlm(bad, bad)
    with pytest.raises(ArticleError, match="999"):
        write_article(stories, DAY, llm, model="m", domains=DOMAINS)
    assert "999" in llm.prompts[1]


def test_bad_format_retries_and_recovers():
    stories = [story(0, "https://www.bloomberg.com/a")]
    llm = FakeLlm("Aquí va la entrada sin cabeceras.", reply())
    art = write_article(stories, DAY, llm, model="m", domains=DOMAINS)
    assert art.main.id == "s0" and "PRINCIPAL" in llm.prompts[1]
