"""Orquestación diaria: fuentes -> guion (+ entrada escrita) -> voz -> publicación en ``site/``.

Códigos de salida: 0 publicó, 1 falló, 2 no hubo suficientes historias.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from radio.audio import mp3_duration
from radio.archive import DayRecord, load_week, atomic_write as _atomic_write, save_day, story_to_archived
from radio.article import write_article
from radio.config import Config, load_config, validate_config
from radio.llm import llm_from_config
from radio.feed import Episode, build_feed, upsert_episode
from radio.script import select_and_write, select_stories
from radio.sources import balance_pool, collect_pool, fetch_bodies
from radio.state import State
from radio.tts import synthesize

log = logging.getLogger(__name__)

MIN_STORIES = 2
LOOKBACK = timedelta(hours=36)
RECENT_DAYS = 3  # días anteriores cuyo contenido ve el selector y el guionista
@dataclass
class Deps:
    claude: object
    tts: object
    http: object
    site_dir: Path
    state_path: Path


@dataclass
class RunResult:
    status: str  # "published" | "skipped" | "failed"
    exit_code: int
    day: date | None = None
    stories: int = 0
    message: str = ""


def estimate_mp3_duration_s(data: bytes) -> int:
    """Duración estimada en segundos (int >= 1)."""
    return max(1, round(mp3_duration(data)))


def _episode_to_json(e: Episode) -> dict:
    return {"day": e.day.isoformat(), "title": e.title, "description": e.description,
            "mp3_path": e.mp3_path, "duration_s": e.duration_s, "size_bytes": e.size_bytes,
            "published": e.published.isoformat() if e.published else None,
            "article_path": e.article_path, "article_title": e.article_title}


def _episode_from_json(d: dict) -> Episode:
    return Episode(day=date.fromisoformat(d["day"]), title=d["title"],
                   description=d["description"], mp3_path=d["mp3_path"],
                   duration_s=int(d["duration_s"]), size_bytes=int(d["size_bytes"]),
                   published=datetime.fromisoformat(d["published"]) if d.get("published") else None,
                   article_path=d.get("article_path"), article_title=d.get("article_title"))


def _load_episodes(path: Path) -> list[Episode]:
    if not path.exists():
        return []
    return [_episode_from_json(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def _recent_days(site_dir: Path, day: date) -> list[DayRecord]:
    """Registros de los ``RECENT_DAYS`` días anteriores a ``day`` (sin el de hoy, para que una
    reejecución del mismo día sea idéntica). Nunca rompe el episodio: ante cualquier error, ninguno."""
    try:
        return load_week(site_dir, day - timedelta(days=1), days=RECENT_DAYS)
    except Exception as exc:
        log.warning("no se pudieron leer los registros recientes (%s); se sigue sin ellos",
                    type(exc).__name__)
        return []


def run(config: Config, now: datetime, deps: Deps) -> RunResult:
    """Ejecuta el pipeline una vez.

    Umbral de día flojo: se cuenta el número de historias NUEVAS (tras filtrar las
    ya usadas, antes de escribir el guion); con menos de 2 no se publica nada
    (exit 2). Con 2-3 el prompt ya produce un episodio corto.
    Solo se escribe en ``site/`` y ``state.json`` al final, tras generar guion y
    audio; cualquier fallo anterior deja todo intacto (exit 1).
    """
    try:
        return _run(config, now, deps)
    except Exception as exc:
        log.exception("pipeline failed")
        return RunResult("failed", 1, message=f"{type(exc).__name__}: {exc}")


def _run(config: Config, now: datetime, deps: Deps) -> RunResult:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    zone = ZoneInfo(config.timezone)
    local_now = now.astimezone(zone)
    day = local_now.date()

    state = State.load(deps.state_path)
    state.current_day = day

    # Etapa 1: pool de titulares+resúmenes (sin cuerpos), balanceado entre fuentes.
    fetched, stats = collect_pool(config.feeds, now - LOOKBACK, client=deps.http)
    feed_note = ""
    if stats.failed * 2 > stats.total:
        feed_note = (f"{stats.failed} de {stats.total} feeds fallaron "
                     "(error o 0 entradas): " + ", ".join(stats.failed_urls))
        log.error("ERROR: %s", feed_note)
    elif stats.failed:
        log.warning("%d de %d feeds fallaron: %s", stats.failed, stats.total,
                    ", ".join(stats.failed_urls))
    suffix = f" | ERROR: {feed_note}" if feed_note else ""

    pool = balance_pool(state.filter_new(fetched), config.pool_size)
    # Etapa 2: Claude elige (llamada barata) y solo entonces se descargan los cuerpos.
    recent = _recent_days(deps.site_dir, day)
    chosen = select_stories(pool, day, deps.claude, config.select_model or config.model,
                            max_stories=config.max_stories, recent=recent)
    if len(chosen) < MIN_STORIES:
        msg = f"Solo {len(chosen)} historias nuevas; no se publica nada{suffix}"
        log.warning(msg)
        return RunResult("skipped", 2, day, len(chosen), msg)
    new = fetch_bodies(chosen, client=deps.http)

    result = select_and_write(new, day, state.pop_corrections(), deps.claude,
                              model=config.model, recent=recent)
    article = None
    if config.trusted_domains:
        # La entrada es un extra: si falla, el episodio se publica igual, sin ella.
        try:
            article = write_article(result.used, day, deps.claude,
                                    model=config.article_model or config.model,
                                    domains=config.trusted_domains)
        except Exception as exc:
            log.warning("sin entrada escrita hoy: %s: %s", type(exc).__name__, exc)
    audio = synthesize(result.text, deps.tts)
    state.mark_used(result.used, day)

    name = f"episodio-{day.isoformat()}.mp3"
    article_path = f"articles/entrada-{day.isoformat()}.json" if article else None
    episode = Episode(
        day=day, title=result.title,
        description=" | ".join(s.title for s in result.used),
        mp3_path=f"episodes/{name}", duration_s=estimate_mp3_duration_s(audio),
        size_bytes=len(audio), published=local_now, article_path=article_path,
        article_title=article.title if article else None)
    episodes_path = deps.site_dir / "episodes.json"
    episodes = upsert_episode(_load_episodes(episodes_path), episode)
    episodes_json = json.dumps([_episode_to_json(e) for e in episodes],
                               ensure_ascii=False, indent=2)
    feed_xml = build_feed(episodes, config.site_url, config.timezone,
                          publish_hour=config.publish_hour)

    # Publicación: MP3 primero, luego episodes.json, luego feed.xml, luego estado.
    _atomic_write(deps.site_dir / "episodes" / name, audio)
    if article:
        _atomic_write(deps.site_dir / article_path, json.dumps(
            article.to_json(day), ensure_ascii=False, indent=2).encode("utf-8"))
    _atomic_write(episodes_path, episodes_json.encode("utf-8"))
    _atomic_write(deps.site_dir / "feed.xml", feed_xml.encode("utf-8"))
    save_day(deps.site_dir, DayRecord(
        day=day, title=result.title, script=result.text,
        stories=[story_to_archived(x) for x in result.used]))
    state.save(deps.state_path)
    msg = (f"Publicado {name} con {len(result.used)} historias"
           f"{' y entrada escrita' if article else ' (sin entrada escrita)'}{suffix}")
    log.info(msg)
    return RunResult("published", 0, day, len(result.used), msg)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from radio.tts import provider_from_config
        config = load_config()
        validate_config(config)
        deps = Deps(claude=llm_from_config(config), tts=provider_from_config(config),
                    http=None, site_dir=Path("site"), state_path=Path("state.json"))
    except Exception as exc:
        # Los mensajes de configuración solo nombran variables (nunca valores de claves).
        log.error("setup failed: %s: %s", type(exc).__name__, exc)
        return 1
    res = run(config, datetime.now(ZoneInfo("UTC")), deps)
    log.info("%s: %s", res.status, res.message)
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
