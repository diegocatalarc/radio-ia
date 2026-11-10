"""Orquestación diaria: fuentes -> guion -> voz -> publicación en ``site/``.

Códigos de salida: 0 publicó, 1 falló, 2 no hubo suficientes historias.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
DEFAULT_BITRATE_BPS = 128_000

# MPEG1 Layer III bitrates (kbps) by header index.
_BITRATES_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]


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
    """Duración estimada en segundos (int >= 1) sin dependencias.

    Salta una etiqueta ID3v2 si existe, lee la cabecera del primer frame MPEG1
    Layer III para obtener el bitrate y calcula ``bytes * 8 / bitrate``. Es exacto
    para CBR (lo que producen OpenAI y ElevenLabs); si no hay cabecera válida se
    asume 128 kbps.
    """
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
               ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        pos = 10 + size
    bitrate = DEFAULT_BITRATE_BPS
    for i in range(pos, min(len(data) - 3, pos + 4096)):
        b1, b2 = data[i], data[i + 1]
        if b1 == 0xFF and (b2 & 0xFE) == 0xFA:  # sync, MPEG1, Layer III
            idx = data[i + 2] >> 4
            if 1 <= idx <= 14:
                bitrate = _BITRATES_KBPS[idx] * 1000
            break
    return max(1, round((len(data) - pos) * 8 / bitrate))


def _episode_to_json(e: Episode) -> dict:
    return {"day": e.day.isoformat(), "title": e.title, "description": e.description,
            "mp3_path": e.mp3_path, "duration_s": e.duration_s, "size_bytes": e.size_bytes,
            "published": e.published.isoformat() if e.published else None}


def _episode_from_json(d: dict) -> Episode:
    return Episode(day=date.fromisoformat(d["day"]), title=d["title"],
                   description=d["description"], mp3_path=d["mp3_path"],
                   duration_s=int(d["duration_s"]), size_bytes=int(d["size_bytes"]),
                   published=datetime.fromisoformat(d["published"]) if d.get("published") else None)


def _load_episodes(path: Path) -> list[Episode]:
    if not path.exists():
        return []
    return [_episode_from_json(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


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
    chosen = select_stories(pool, day, deps.claude, config.model,
                            max_stories=config.max_stories)
    if len(chosen) < MIN_STORIES:
        msg = f"Solo {len(chosen)} historias nuevas; no se publica nada{suffix}"
        log.warning(msg)
        return RunResult("skipped", 2, day, len(chosen), msg)
    new = fetch_bodies(chosen, client=deps.http)

    result = select_and_write(new, day, state.pop_corrections(), deps.claude,
                              model=config.model)
    audio = synthesize(result.text, deps.tts)
    state.mark_used(result.used, day)

    name = f"episodio-{day.isoformat()}.mp3"
    episode = Episode(
        day=day, title=result.title,
        description=" | ".join(s.title for s in result.used),
        mp3_path=f"episodes/{name}", duration_s=estimate_mp3_duration_s(audio),
        size_bytes=len(audio), published=local_now)
    episodes_path = deps.site_dir / "episodes.json"
    episodes = upsert_episode(_load_episodes(episodes_path), episode)
    episodes_json = json.dumps([_episode_to_json(e) for e in episodes],
                               ensure_ascii=False, indent=2)
    feed_xml = build_feed(episodes, config.site_url, config.timezone,
                          publish_hour=config.publish_hour)

    # Publicación: MP3 primero, luego episodes.json, luego feed.xml, luego estado.
    _atomic_write(deps.site_dir / "episodes" / name, audio)
    _atomic_write(episodes_path, episodes_json.encode("utf-8"))
    _atomic_write(deps.site_dir / "feed.xml", feed_xml.encode("utf-8"))
    state.save(deps.state_path)
    msg = f"Publicado {name} con {len(result.used)} historias{suffix}"
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
