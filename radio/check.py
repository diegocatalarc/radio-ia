"""Utilidades de despliegue: ¿ya hay episodio de hoy? y limpieza de MP3 huérfanos.

``python -m radio.check``          exit 0 si ya existe el episodio de hoy, 1 si no.
``python -m radio.check --prune``  borra MP3 de ``site/episodes`` que ``episodes.json`` ya no
                                   referencia (el feed solo conserva 60 episodios).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from radio.config import load_config


def _read_episodes(site_dir: Path) -> list[dict]:
    path = Path(site_dir) / "episodes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def episode_exists_today(site_dir, tz: str, now: datetime) -> bool:
    """True si ``episodes.json`` ya tiene un episodio con la fecha de hoy en ``tz``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.astimezone(ZoneInfo(tz)).date().isoformat()
    return any(e.get("day") == today for e in _read_episodes(Path(site_dir)))


def prune_unreferenced_mp3(site_dir) -> list[str]:
    """Borra los .mp3 de ``episodes/`` no referenciados; devuelve los nombres borrados.

    Si no existe ``episodes.json`` no borra nada (evita vaciar el sitio por error).
    """
    site = Path(site_dir)
    if not (site / "episodes.json").exists():
        return []
    keep = {Path(e["mp3_path"]).name for e in _read_episodes(site)}
    removed = []
    for f in sorted((site / "episodes").glob("*.mp3")):
        if f.name not in keep:
            f.unlink()
            removed.append(f.name)
    return removed


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    site = Path("site")
    if "--prune" in argv:
        for name in prune_unreferenced_mp3(site):
            print(f"borrado {name}")
        return 0
    config = load_config()
    now = datetime.now(ZoneInfo("UTC"))
    return 0 if episode_exists_today(site, config.timezone, now) else 1


if __name__ == "__main__":
    sys.exit(main())
