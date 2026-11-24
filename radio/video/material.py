"""Material de la semana: historias y guiones diarios como ``Story`` para el chequeo de cifras."""
from __future__ import annotations

from datetime import datetime, time, timezone

from radio.archive import DayRecord
from radio.models import Story


def week_material(week: list[DayRecord]) -> list[Story]:
    """Historias archivadas (sin repetir ids) más un ``Story`` por cada guion diario."""
    out: list[Story] = []
    seen: set[str] = set()
    for rec in week:
        stamp = datetime.combine(rec.day, time(), tzinfo=timezone.utc)
        for a in rec.stories:
            if a.id in seen:
                continue
            seen.add(a.id)
            out.append(Story(id=a.id, title=a.title, url=a.url, source=a.source,
                             published=stamp, summary=a.summary, body=a.body))
        out.append(Story(id=f"_script-{rec.day.isoformat()}", title=rec.title, url="",
                         source="guion diario", published=stamp, summary="", body=rec.script))
    return out


def render_previous(previous: list[dict] | None) -> str:
    """Semanas ya publicadas (etiqueta, título y tesis) para que no se repita su discurso."""
    lines = []
    for e in previous or []:
        thesis = f" Tesis: {e['thesis']}" if e.get("thesis") else ""
        lines.append(f"- {e.get('label', '')}: {e.get('title', '')}.{thesis}")
    return "\n".join(lines) or "(ninguna)"
