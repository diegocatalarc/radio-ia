"""Escritura del guion con Claude y control de que las cifras vengan de las fuentes."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from radio.models import Story

PROMPT_PATH = Path(__file__).parent / "prompts" / "script_es.md"
DEFAULT_MODEL = "claude-sonnet-5-5"

_TAG_RE = re.compile(r"<[^>]*>")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


class ScriptGroundingError(Exception):
    """El guion contiene cifras que no aparecen en las fuentes."""


@dataclass
class ScriptResult:
    text: str
    used: list[Story]
    title: str


def _clean(text: str | None) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _numbers(text: str) -> set[str]:
    found: set[str] = set()
    for tok in _NUM_RE.findall(text):
        found.add(tok)
        found.add(re.sub(r"[.,]", "", tok))  # 1.300 == 1,300 == 1300
        found.add(tok.replace(",", "."))
    return found


def unsupported_numbers(text: str, stories: list[Story]) -> list[str]:
    """Cifras del guion que no aparecen en ningún título, resumen o cuerpo."""
    allowed: set[str] = set()
    for s in stories:
        allowed |= _numbers(" ".join([s.title, _clean(s.summary), _clean(s.body)]))
    bad: list[str] = []
    for tok in _NUM_RE.findall(_clean(text)):
        variants = {tok, re.sub(r"[.,]", "", tok), tok.replace(",", ".")}
        if not variants & allowed and tok not in bad:
            bad.append(tok)
    return bad


def _render_story(s: Story) -> str:
    head = f"[id: {s.id}] {s.title}\nFuente: {s.source} ({s.url})\nResumen: {_clean(s.summary)}"
    if s.body is None:
        return head + "\n(SOLO TITULAR Y RESUMEN: no afirmes ningún detalle más allá de esto.)"
    return head + f"\nTexto completo: {_clean(s.body)}"


def _build_prompt(stories: list[Story], today: date, corrections: list[str],
                  extra: str = "") -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    corr = "\n".join(f"- {c}" for c in corrections) or "(ninguna)"
    prompt = (tpl.replace("{{FECHA}}", today.strftime("%d/%m/%Y"))
              .replace("{{CORRECCIONES}}", corr)
              .replace("{{HISTORIAS}}", "\n\n".join(_render_story(s) for s in stories)))
    return prompt + extra


def _parse(raw: str, stories: list[Story]) -> ScriptResult:
    title = ""
    used_ids: list[str] = []
    lines = raw.strip().splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"\s*(TITULO|TÍTULO|USADAS)\s*:\s*(.*)", lines[i], re.I)
        if m:
            if m.group(1).upper().startswith("T"):
                title = m.group(2).strip()
            else:
                used_ids = [x.strip() for x in m.group(2).split(",") if x.strip()]
            i += 1
        elif not lines[i].strip() and i < 3:
            i += 1
        else:
            break
    text = "\n".join(lines[i:]).strip()
    by_id = {s.id: s for s in stories}
    used = [by_id[x] for x in dict.fromkeys(used_ids) if x in by_id]
    return ScriptResult(text=text, used=used, title=title)


def select_and_write(stories: list[Story], today: date, corrections: list[str],
                     client, *, model: str = DEFAULT_MODEL) -> ScriptResult:
    # La fecha de hoy es legítima en la apertura: se admite como "fuente".
    date_src = Story(id="_today", title=today.strftime("%d/%m/%Y %d %m %Y"), url="",
                     source="", published=None, summary="")  # type: ignore[arg-type]
    extra = ""
    bad: list[str] = []
    for _ in range(2):
        prompt = _build_prompt(stories, today, corrections, extra)
        resp = client.messages.create(model=model, max_tokens=8000,
                                      messages=[{"role": "user", "content": prompt}])
        result = _parse(resp.content[0].text, stories)
        bad = unsupported_numbers(result.text, stories + [date_src])
        if not bad:
            return result
        extra = ("\n\nATENCIÓN: tu intento anterior incluía cifras ausentes de las fuentes: "
                 + ", ".join(bad) + ". Reescribe el guion sin ellas.")
    raise ScriptGroundingError("Cifras no respaldadas por las fuentes: " + ", ".join(bad))
