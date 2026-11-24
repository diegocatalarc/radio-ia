"""Director: lee la semana y decide la tesis y los hilos del video."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from radio.archive import DayRecord
from radio.llm import Llm
from radio.script import _clean, unsupported_numbers
from radio.models import Story
from radio.video.material import render_previous, week_material

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "director_es.md"
MAX_TOKENS = 4000
_FENCE_RE = re.compile(r"^\s*```\w*\s*|\s*```\s*$")


class DirectorError(Exception):
    """El Director no produjo un briefing válido tras reintentar."""


@dataclass
class Thread:
    title: str
    angle: str
    story_ids: list[str]
    figures: list[str]
    short: bool
    arc: str = ""


@dataclass
class Briefing:
    thesis: str
    threads: list[Thread]


def _render_days(week: list[DayRecord]) -> str:
    blocks = []
    for rec in week:
        stories = "\n\n".join(
            f'<fuente id="{a.id}">\n[id: {a.id}] {_clean(a.title)}\nFuente: {a.source}\n'
            f'Resumen: {_clean(a.summary)[:300]}\n</fuente>' for a in rec.stories)
        blocks.append(f"## {rec.day.isoformat()} — {_clean(rec.title)}\n"
                      f"<guion>\n{rec.script}\n</guion>\n\n{stories}")
    return "\n\n".join(blocks)


def _build_prompt(week: list[DayRecord], previous: list[dict] | None, extra: str) -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    return (tpl.replace("{{DESDE}}", week[0].day.isoformat())
            .replace("{{HASTA}}", week[-1].day.isoformat())
            .replace("{{ANTERIORES}}", render_previous(previous))
            .replace("{{DIAS}}", _render_days(week))) + extra


def _validate(raw: str, week: list[DayRecord], material: list[Story]) -> Briefing:
    try:
        data = json.loads(_FENCE_RE.sub("", raw.strip()))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc}") from None
    if not isinstance(data, dict) or not str(data.get("thesis") or "").strip():
        raise ValueError("falta 'thesis'")
    raw_threads = data.get("threads")
    if not isinstance(raw_threads, list) or not 3 <= len(raw_threads) <= 4:
        raise ValueError("debe haber 3 o 4 hilos en 'threads'")
    known = {a.id for rec in week for a in rec.stories}
    threads: list[Thread] = []
    for t in raw_threads:
        ids = [str(i) for i in (t.get("story_ids") or [])]
        unknown = [i for i in ids if i not in known]
        if not ids or unknown:
            raise ValueError("story_ids inexistentes o vacíos: " + ", ".join(unknown or ["(vacío)"]))
        threads.append(Thread(title=str(t.get("title") or "").strip(),
                              angle=str(t.get("angle") or "").strip(), story_ids=ids,
                              figures=[str(f) for f in (t.get("figures") or [])],
                              short=bool(t.get("short")), arc=str(t.get("arc") or "").strip()))
    all_ids = [i for t in threads for i in t.story_ids]
    repeated = sorted({i for i in all_ids if all_ids.count(i) > 1})
    if repeated:
        raise ValueError("historias en más de un hilo (cada una va en uno solo): " + ", ".join(repeated))
    if not any(t.short for t in threads):
        raise ValueError("marca al menos un hilo con short: true")
    bad = unsupported_numbers(" ".join(f for t in threads for f in t.figures), material)
    if bad:
        raise ValueError("cifras no respaldadas por las fuentes: " + ", ".join(bad))
    return Briefing(thesis=str(data["thesis"]).strip(), threads=threads)


def direct(week: list[DayRecord], client: Llm, model: str,
           previous: list[dict] | None = None) -> Briefing:
    material = week_material(week)
    extra = problem = ""
    for _ in range(2):
        reply = client.complete(_build_prompt(week, previous, extra), model=model, max_tokens=MAX_TOKENS)
        try:
            return _validate(reply.text or "", week, material)
        except ValueError as exc:
            problem = str(exc)
            extra = f"\n\nATENCIÓN: tu intento anterior no era válido: {problem}. Corrígelo."
    raise DirectorError("Briefing no válido tras reintento: " + problem)
