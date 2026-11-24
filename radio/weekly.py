"""Video semanal: registros diarios -> Director -> Editor -> voz -> Remotion -> ``site/weekly/``.

Códigos de salida: 0 publicó (o ya existía), 1 falló, 2 hay menos de 4 registros diarios.
``python -m radio.weekly --force`` regenera aunque la semana ya esté publicada.
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from radio.archive import atomic_write, load_week
from radio.config import Config, load_config, validate_config
from radio.llm import Llm, llm_from_config
from radio.run import RunResult
from radio.tts import TtsProvider
from radio.video.director import direct
from radio.video.editor import write_scenes
from radio.video.manifest import build_manifest, week_label
from radio.video.render import render_video
from radio.video.voice import narrate

log = logging.getLogger(__name__)

MIN_DAYS = 4
KEEP_WEEKS = 4
PREVIOUS_WEEKS = 2
FORMATS = (("16x9", "Semanal16x9", False), ("9x16", "Semanal9x16", True))


@dataclass
class WeeklyDeps:
    llm: Llm
    tts: TtsProvider
    site_dir: Path
    work_dir: Path
    render: Callable[..., None] = render_video


def week_id(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _load_index(site_dir: Path) -> list[dict]:
    path = Path(site_dir) / "weekly.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def weekly_exists(site_dir: Path, wid: str) -> bool:
    return any(e.get("week") == wid for e in _load_index(site_dir))


def run_weekly(config: Config, now: datetime, deps: WeeklyDeps, *, force: bool = False) -> RunResult:
    try:
        return _run_weekly(config, now, deps, force)
    except Exception as exc:
        log.exception("weekly pipeline failed")
        return RunResult("failed", 1, message=f"{type(exc).__name__}: {exc}")


def _run_weekly(config: Config, now: datetime, deps: WeeklyDeps, force: bool) -> RunResult:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = now.astimezone(ZoneInfo(config.timezone)).date()
    wid = week_id(day)
    if weekly_exists(deps.site_dir, wid) and not force:
        return RunResult("skipped", 0, day, 0, f"El video de {wid} ya existe; no se hace nada")
    week = load_week(deps.site_dir, day)
    if len(week) < MIN_DAYS:
        msg = f"Solo {len(week)} registros diarios (mínimo {MIN_DAYS}); no se publica nada"
        log.warning(msg)
        return RunResult("skipped", 2, day, len(week), msg)

    model = config.weekly_model or config.model
    # Semanas ya publicadas (las 2 más recientes, sin la actual) para no repetir su discurso.
    previous = sorted((e for e in _load_index(deps.site_dir) if e.get("week") != wid),
                      key=lambda e: e["week"], reverse=True)[:PREVIOUS_WEEKS]
    briefing = direct(week, deps.llm, model, previous)
    script = write_scenes(briefing, week, deps.llm, model, previous)
    audios = narrate(script, deps.tts)
    label = week_label([r.day for r in week])

    work = Path(deps.work_dir)
    outputs: dict[str, Path] = {}
    for tag, composition, vertical in FORMATS:
        fmt_dir = work / tag
        props = build_manifest(script, audios, fmt_dir, vertical=vertical, week_label=label)
        out = work / f"{wid}-{tag}.mp4"
        deps.render(props, fmt_dir, composition, out)
        outputs[tag] = out

    # Publicación: MP4 primero, luego weekly.json, luego se borran los MP4 huérfanos.
    site = Path(deps.site_dir)
    for tag, out in outputs.items():
        atomic_write(site / "weekly" / out.name, out.read_bytes())
    entry = {"week": wid, "label": label, "title": script.title, "thesis": briefing.thesis,
             "video_16x9": f"weekly/{wid}-16x9.mp4", "video_9x16": f"weekly/{wid}-9x16.mp4",
             "published": now.astimezone(ZoneInfo(config.timezone)).isoformat()}
    index = [e for e in _load_index(site) if e.get("week") != wid] + [entry]
    index = sorted(index, key=lambda e: e["week"], reverse=True)[:KEEP_WEEKS]
    atomic_write(site / "weekly.json", json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
    keep = {Path(e[k]).name for e in index for k in ("video_16x9", "video_9x16")}
    for f in (site / "weekly").glob("*.mp4"):
        if f.name not in keep:
            f.unlink()
    msg = f"Publicado el video {wid} con {len(script.scenes)} escenas"
    log.info(msg)
    return RunResult("published", 0, day, len(week), msg)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from radio.tts import provider_from_config
        config = load_config()
        validate_config(config)
        llm, tts = llm_from_config(config), provider_from_config(config)
    except Exception as exc:
        log.error("setup failed: %s: %s", type(exc).__name__, exc)
        return 1
    with tempfile.TemporaryDirectory(prefix="radio-weekly-") as tmp:
        deps = WeeklyDeps(llm=llm, tts=tts, site_dir=Path("site"), work_dir=Path(tmp))
        res = run_weekly(config, datetime.now(ZoneInfo("UTC")), deps, force="--force" in argv)
    log.info("%s: %s", res.status, res.message)
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
