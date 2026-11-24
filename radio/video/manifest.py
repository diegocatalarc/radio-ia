"""Manifiesto de render: escenas + audio -> ``props.json`` y archivos que consume Remotion."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from radio.archive import atomic_write
from radio.video.scenes import Scene, SceneScript, short_scenes
from radio.video.voice import SceneAudio

FPS = 30
TAIL_S = 0.5  # silencio al final de cada escena

_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"]


def week_label(days: list[date]) -> str:
    """Rango legible de la semana, p. ej. ``17–23 de noviembre de 2026``."""
    a, b = min(days), max(days)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b.day} de {_MONTHS[a.month - 1]} de {a.year}"
    if a.year == b.year:
        return (f"{a.day} de {_MONTHS[a.month - 1]} – {b.day} de {_MONTHS[b.month - 1]} "
                f"de {b.year}")
    return (f"{a.day} de {_MONTHS[a.month - 1]} de {a.year} – "
            f"{b.day} de {_MONTHS[b.month - 1]} de {b.year}")


def _scene_props(s: Scene, audio: SceneAudio) -> dict:
    return {
        "id": s.id, "kind": s.kind, "onScreen": s.on_screen, "value": s.value,
        "chart": [{"label": l, "value": v} for l, v in s.chart] if s.chart else None,
        "timeline": [{"when": w, "label": l} for w, l in s.timeline] if s.timeline else None,
        "source": s.source, "audio": f"audio/{s.id}.mp3",
        "durationFrames": math.ceil((audio.duration_s + TAIL_S) * FPS),
    }


def build_manifest(script: SceneScript, audios: list[SceneAudio], out_dir: Path, *,
                   vertical: bool, week_label: str) -> Path:
    by_id = {a.scene_id: a for a in audios}
    scenes = short_scenes(script) if vertical else script.scenes
    out_dir = Path(out_dir)
    for s in scenes:
        atomic_write(out_dir / "audio" / f"{s.id}.mp3", by_id[s.id].mp3)
    props = {"fps": FPS, "title": script.title, "weekLabel": week_label,
             "scenes": [_scene_props(s, by_id[s.id]) for s in scenes]}
    path = out_dir / "props.json"
    atomic_write(path, json.dumps(props, ensure_ascii=False, indent=2).encode("utf-8"))
    return path
