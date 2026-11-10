"""Escritura del guion con Claude y control de que las cifras vengan de las fuentes."""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from radio.models import Story

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "script_es.md"
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 8000

_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"]
_TAG_RE = re.compile(r"<[^>]*>")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_FENCE_RE = re.compile(r"^\s*```\w*\s*$")
_HEADER_RE = re.compile(
    r"^\s*[*_#>\s]*(TITULO|TÍTULO|USADAS)\s*[*_]*\s*:\s*[*_]*\s*(.*)$", re.I)


class ScriptGroundingError(Exception):
    """El guion contiene cifras que no aparecen en las fuentes (o no es parseable)."""


class ScriptTruncatedError(Exception):
    """La respuesta del modelo se cortó por max_tokens."""


@dataclass
class ScriptResult:
    text: str
    used: list[Story]
    title: str


def _clean(text: str | None) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _canon(tok: str) -> str:
    """Forma canónica: miles sin separador; decimales con punto (1,5 == 1.5)."""
    if _THOUSANDS_RE.match(tok):
        return re.sub(r"[.,]", "", tok)
    return tok.replace(",", ".")


def unsupported_numbers(text: str, stories: list[Story]) -> list[str]:
    """Cifras del guion que no aparecen en ningún título, resumen o cuerpo.

    Límites conocidos: la comparación está agrupada entre todas las historias (una
    cifra de una historia respalda a otra) y solo mira dígitos: ignora las palabras
    de magnitud ("mil millones" vs "millones") y las cifras escritas con palabras.
    """
    allowed: set[str] = set()
    for s in stories:
        src = " ".join([s.title, _clean(s.summary), _clean(s.body)])
        allowed |= {_canon(t) for t in _NUM_RE.findall(src)}
    bad: list[str] = []
    for tok in _NUM_RE.findall(_clean(text)):
        if _canon(tok) not in allowed and tok not in bad:
            bad.append(tok)
    return bad


def _render_story(s: Story) -> str:
    head = f"[id: {s.id}] {s.title}\nFuente: {s.source} ({s.url})\nResumen: {_clean(s.summary)}"
    if s.body is None:
        return head + "\n(SOLO TITULAR Y RESUMEN: no afirmes ningún detalle más allá de esto.)"
    return head + f"\nTexto completo: {_clean(s.body)}"


def _spoken_date(d: date) -> str:
    return f"{d.day} de {_MONTHS[d.month - 1]} de {d.year}"


def _build_prompt(stories: list[Story], today: date, corrections: list[str],
                  extra: str = "") -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    corr = "\n".join(f"- {c}" for c in corrections) or "(ninguna)"
    prompt = (tpl.replace("{{FECHA_HABLADA}}", _spoken_date(today))
              .replace("{{CORRECCIONES}}", corr)
              .replace("{{HISTORIAS}}", "\n\n".join(_render_story(s) for s in stories)))
    return prompt + extra


def _parse(raw: str, stories: list[Story]) -> tuple[ScriptResult | None, str | None]:
    """Devuelve (resultado, error). El error describe qué falta si no es válido."""
    lines = [ln for ln in raw.strip().splitlines() if not _FENCE_RE.match(ln)]
    title = ""
    used_ids: list[str] = []
    i = 0
    while i < len(lines):
        m = _HEADER_RE.match(lines[i])
        if m:
            val = m.group(2).strip(" *_")
            if m.group(1).upper().startswith("T"):
                title = val
            else:
                used_ids = [x.strip(" *_`") for x in val.split(",") if x.strip(" *_`")]
            i += 1
        elif not lines[i].strip():
            i += 1
        else:
            break
    text = "\n".join(lines[i:]).strip()
    by_id = {s.id: s for s in stories}
    used = [by_id[x] for x in dict.fromkeys(used_ids) if x in by_id]
    if not title or not used or not text:
        return None, ("Tu respuesta debe empezar con las líneas 'TITULO: ...' y "
                      "'USADAS: id1,id2' (ids exactos de las historias), seguidas del guion.")
    return ScriptResult(text=text, used=used, title=title), None


def _response_text(resp) -> str | None:
    for block in getattr(resp, "content", None) or []:
        t = getattr(block, "text", None)
        if isinstance(t, str) and t.strip():
            return t
    return None


def select_and_write(stories: list[Story], today: date, corrections: list[str],
                     client, *, model: str = DEFAULT_MODEL) -> ScriptResult:
    # Fuentes admitidas además de las historias: la fecha de hoy y las correcciones.
    extra_src = [
        Story(id="_today", title=f"{today.day} {today.month} {today.year} "
              + today.strftime("%d/%m/%Y"), url="", source="",
              published=None, summary=""),  # type: ignore[arg-type]
        Story(id="_corr", title=" ".join(corrections), url="", source="",
              published=None, summary=""),  # type: ignore[arg-type]
    ]
    feedback = ""
    problem = ""
    for _ in range(2):
        prompt = _build_prompt(stories, today, corrections, feedback)
        resp = client.messages.create(model=model, max_tokens=MAX_TOKENS,
                                      messages=[{"role": "user", "content": prompt}])
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ScriptTruncatedError("La respuesta se truncó por max_tokens")
        raw = _response_text(resp)
        if raw is None:
            problem = "la respuesta no contiene texto"
            feedback = "\n\nATENCIÓN: tu intento anterior no contenía texto. Responde con el guion."
            continue
        result, err = _parse(raw, stories)
        if result is None:
            problem = err
            feedback = "\n\nATENCIÓN: " + err
            continue
        bad = unsupported_numbers(result.text, stories + extra_src)
        if bad:
            problem = "cifras no respaldadas por las fuentes: " + ", ".join(bad)
            feedback = ("\n\nATENCIÓN: tu intento anterior incluía cifras ausentes de las "
                        "fuentes: " + ", ".join(bad) + ". Reescribe el guion sin ellas.")
            continue
        words = len(result.text.split())
        if not 1300 <= words <= 1600:
            log.warning("Guion de %d palabras (objetivo 1300-1600)", words)
        return result
    raise ScriptGroundingError("Guion no válido tras reintento: " + problem)
