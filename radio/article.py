"""Entrada escrita del día: una noticia relevante contada en profundidad.

Solo se alimenta de historias cuya URL pertenece a un medio de ``trusted_domains`` (medios con
redacción y estándares editoriales; nada de blogs corporativos ni agregadores) y de las que se
pudo extraer el texto completo. Las cifras pasan el mismo control que el guion: toda cifra del
texto debe aparecer en las fuentes. Si algo falla, el episodio se publica igual, sin entrada.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from radio.models import Story
from radio.script import (_FENCE_RE, _clean, _generate, _response_text, _spoken_date,
                          unsupported_numbers)

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "article_es.md"
MIN_WORDS = 500
MAX_WORDS = 1100
MAX_SOURCES = 4
_HEADER_RE = re.compile(
    r"^\s*[*_#>\s]*(TITULO|TÍTULO|PRINCIPAL|FUENTES|ENTRADILLA)\s*[*_]*\s*:\s*[*_]*\s*(.*)$", re.I)
_MD_RE = re.compile(r"^\s*(?:#+|[-*•]|\d+[.)])\s+")


# Nombre del medio por dominio: el título del feed a veces es una sección ("Tech", "AI | The Verge").
OUTLET_NAMES = {
    "bloomberg.com": "Bloomberg", "economist.com": "The Economist",
    "theguardian.com": "The Guardian", "technologyreview.com": "MIT Technology Review",
    "cnbc.com": "CNBC", "wired.com": "Wired", "theverge.com": "The Verge",
    "techcrunch.com": "TechCrunch", "fastcompany.com": "Fast Company",
    "reuters.com": "Reuters", "apnews.com": "AP", "ft.com": "Financial Times",
    "wsj.com": "The Wall Street Journal", "nytimes.com": "The New York Times",
    "elpais.com": "El País", "bbc.com": "BBC", "bbc.co.uk": "BBC",
}


def outlet(s: Story) -> str:
    host = (urlparse(s.url).hostname or "").lower()
    for domain, name in OUTLET_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return s.source


class ArticleError(Exception):
    """No se pudo escribir una entrada válida (sin fuentes confiables, cifras sin respaldo...)."""


@dataclass
class Article:
    title: str
    lede: str
    paragraphs: list[str]
    main: Story
    sources: list[Story] = field(default_factory=list)

    def to_json(self, day: date) -> dict:
        return {
            "day": day.isoformat(), "title": self.title, "lede": self.lede,
            "body": self.paragraphs,
            "sources": [{"title": _clean(s.title), "source": outlet(s), "url": s.url}
                        for s in self.sources],
        }


def is_trusted(url: str, domains: list[str]) -> bool:
    """True si el host de ``url`` es uno de ``domains`` o un subdominio suyo (solo https/http)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not host:
        return False
    return any(host == d or host.endswith("." + d)
               for d in (x.lower().strip().lstrip(".") for x in domains) if d)


def trusted_candidates(stories: list[Story], domains: list[str]) -> list[Story]:
    """Historias de medios confiables con texto completo (solo con cuerpo hay profundidad)."""
    return [s for s in stories if s.body and is_trusted(s.url, domains)]


def _render(s: Story) -> str:
    return (f'<fuente id="{s.id}">\n[id: {s.id}] {_clean(s.title)}\n'
            f"Medio: {outlet(s)} ({s.url})\nResumen: {_clean(s.summary)}\n"
            f"Texto completo: {_clean(s.body)}\n</fuente>")


def _build_prompt(stories: list[Story], today: date, extra: str = "") -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    return (tpl.replace("{{FECHA_HABLADA}}", _spoken_date(today))
            .replace("{{PALABRAS_MIN}}", str(MIN_WORDS))
            .replace("{{PALABRAS_MAX}}", str(MAX_WORDS))
            .replace("{{HISTORIAS}}", "\n\n".join(_render(s) for s in stories))) + extra


def _ids(val: str) -> list[str]:
    return [x.strip(" *_`[]") for x in val.split(",") if x.strip(" *_`[]")]


def _parse(raw: str, stories: list[Story]) -> tuple[Article | None, str | None]:
    lines = [ln for ln in raw.strip().splitlines() if not _FENCE_RE.match(ln)]
    head: dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = _HEADER_RE.match(lines[i])
        if m:
            key = m.group(1).upper().replace("Í", "I")
            head[key] = m.group(2).strip(" *_")
            i += 1
        elif not lines[i].strip():
            i += 1
        else:
            break
    by_id = {s.id: s for s in stories}
    main_ids = [x for x in _ids(head.get("PRINCIPAL", "")) if x in by_id]
    main = by_id[main_ids[0]] if main_ids else None
    sources: list[Story] = [main] if main else []
    for x in _ids(head.get("FUENTES", "")):
        if x in by_id and by_id[x] not in sources:
            sources.append(by_id[x])
    paragraphs = []
    for block in re.split(r"\n\s*\n", "\n".join(lines[i:])):
        text = " ".join(_MD_RE.sub("", ln).strip() for ln in block.splitlines()).strip()
        text = text.replace("**", "")
        if text:
            paragraphs.append(text)
    title = head.get("TITULO", "")
    lede = head.get("ENTRADILLA", "")
    if not (title and lede and main and paragraphs):
        return None, ("Tu respuesta debe empezar con las líneas 'TITULO: ...', "
                      "'PRINCIPAL: <id>', 'FUENTES: id1,id2' y 'ENTRADILLA: ...' (ids exactos), "
                      "seguidas del cuerpo en párrafos separados por una línea en blanco.")
    return Article(title=title, lede=lede, paragraphs=paragraphs, main=main,
                   sources=sources[:MAX_SOURCES]), None


def write_article(stories: list[Story], today: date, client, *, model: str,
                  domains: list[str]) -> Article:
    """Elige la noticia más relevante entre las de medios confiables y la desarrolla.

    ``stories`` son las historias del episodio (ya con cuerpo); solo se usan las de
    ``domains``. Lanza :class:`ArticleError` si no hay fuentes o la entrada no es válida.
    """
    pool = trusted_candidates(stories, domains)
    if not pool:
        raise ArticleError("ninguna historia de un medio confiable con texto completo")
    today_src = Story(id="_today", title=f"{today.day} {today.month} {today.year}", url="",
                      source="", published=None, summary="")  # type: ignore[arg-type]
    feedback = ""
    problem = ""
    for _ in range(2):
        resp = _generate(client, model, _build_prompt(pool, today, feedback))
        raw = _response_text(resp)
        if raw is None:
            problem = "la respuesta no contiene texto"
            feedback = "\n\nATENCIÓN: tu intento anterior no contenía texto."
            continue
        art, err = _parse(raw, pool)
        if art is None:
            problem = err or ""
            feedback = "\n\nATENCIÓN: " + problem
            continue
        # Las cifras solo pueden venir de las fuentes que la entrada cita.
        text = " ".join([art.title, art.lede, *art.paragraphs])
        bad = unsupported_numbers(text, art.sources + [today_src])
        if bad:
            problem = "cifras no respaldadas por las fuentes citadas: " + ", ".join(bad)
            feedback = ("\n\nATENCIÓN: tu intento anterior incluía cifras ausentes de las "
                        "fuentes que citas en FUENTES: " + ", ".join(bad) + ". Reescribe sin "
                        "ellas o añade a FUENTES la fuente que las contiene.")
            continue
        words = len(text.split())
        if not MIN_WORDS * 0.8 <= words <= MAX_WORDS * 1.2:
            log.warning("Entrada de %d palabras (objetivo %d-%d)", words, MIN_WORDS, MAX_WORDS)
        return art
    raise ArticleError("Entrada no válida tras reintento: " + problem)
