"""Editor: convierte el briefing del Director en un guion de escenas verificado."""
from __future__ import annotations

import re
from pathlib import Path

from radio.archive import DayRecord
from radio.llm import Llm
from radio.script import _clean, unsupported_numbers
from radio.video.director import Briefing
from radio.video.material import render_previous, week_material
from radio.video.scenes import SceneError, SceneScript, parse_scene_script, scene_texts

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "editor_es.md"
MAX_TOKENS = 12000


class EditorError(Exception):
    """El Editor no produjo un guion de escenas válido tras reintentar."""


def _render_briefing(b: Briefing) -> str:
    lines = [f"Tesis: {b.thesis}"]
    for t in b.threads:
        lines.append(f"- Hilo{' (short)' if t.short else ''}: {t.title}. {t.angle} "
                     f"Historias: {', '.join(t.story_ids)}. "
                     f"Cifras: {'; '.join(t.figures) or 'ninguna'}."
                     + (f" Evolución: {t.arc}" if t.arc else ""))
    return "\n".join(lines)


def _build_prompt(briefing: Briefing, week: list[DayRecord], previous: list[dict] | None,
                  extra: str) -> str:
    wanted = {i for t in briefing.threads for i in t.story_ids}
    seen: set[str] = set()
    stories = []
    for rec in week:
        for a in rec.stories:
            if a.id in wanted and a.id not in seen:
                seen.add(a.id)
                body = f"\nTexto completo: {_clean(a.body)}" if a.body else ""
                stories.append(f'<fuente id="{a.id}">\n[id: {a.id}] {_clean(a.title)}\n'
                               f"Fuente: {a.source} ({a.url})\nResumen: {_clean(a.summary)}"
                               f"{body}\n</fuente>")
    scripts = "\n\n".join(f"<guion fecha=\"{r.day.isoformat()}\">\n{r.script}\n</guion>" for r in week)
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    return (tpl.replace("{{DESDE}}", week[0].day.isoformat())
            .replace("{{HASTA}}", week[-1].day.isoformat())
            .replace("{{BRIEFING}}", _render_briefing(briefing))
            .replace("{{ANTERIORES}}", render_previous(previous))
            .replace("{{HISTORIAS}}", "\n\n".join(stories))
            .replace("{{GUIONES}}", scripts)) + extra


_WORD_RE = re.compile(r"[a-záéíóúñü]+")
REPEAT_THRESHOLD = 0.5
MIN_CONTENT_WORDS = 8


def repeated_scenes(script: SceneScript) -> list[tuple[str, str]]:
    """Pares de escenas cuya narración comparte la mitad o más de su vocabulario (se repiten)."""
    bags = [(s.id, {w for w in _WORD_RE.findall(s.narration.lower()) if len(w) > 3})
            for s in script.scenes]
    out = []
    for i, (a, wa) in enumerate(bags):
        for b, wb in bags[i + 1:]:
            if len(wa) >= MIN_CONTENT_WORDS and len(wb) >= MIN_CONTENT_WORDS \
                    and len(wa & wb) / len(wa | wb) >= REPEAT_THRESHOLD:
                out.append((a, b))
    return out


def write_scenes(briefing: Briefing, week: list[DayRecord], client: Llm, model: str,
                 previous: list[dict] | None = None) -> SceneScript:
    material = week_material(week)
    extra = problem = ""
    for _ in range(2):
        reply = client.complete(_build_prompt(briefing, week, previous, extra), model=model,
                                max_tokens=MAX_TOKENS)
        try:
            script = parse_scene_script(reply.text or "")
        except SceneError as exc:
            problem = str(exc)
            extra = f"\n\nATENCIÓN: tu intento anterior no era válido: {problem}. Corrígelo."
            continue
        bad = unsupported_numbers(scene_texts(script), material)
        if bad:
            problem = "cifras no respaldadas por el material: " + ", ".join(bad)
            extra = ("\n\nATENCIÓN: tu intento anterior incluía cifras ausentes del material: "
                     + ", ".join(bad) + ". Reescribe sin ellas; las cantidades que no vienen "
                     "de las fuentes se escriben con palabras, nunca con dígitos.")
            continue
        dups = repeated_scenes(script)
        if dups:
            pairs = ", ".join(f"{a} y {b}" for a, b in dups)
            problem = "escenas que repiten lo mismo: " + pairs
            extra = (f"\n\nATENCIÓN: tu intento anterior repite el mismo contenido en las escenas {pairs}. "
                     "Cada escena debe aportar algo nuevo; un hecho de varios días se cuenta una sola vez, "
                     "con su evolución. Reescribe sin repetir.")
            continue
        return script
    raise EditorError("Guion de escenas no válido tras reintento: " + problem)
