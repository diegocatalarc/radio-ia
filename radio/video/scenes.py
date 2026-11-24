"""Esquema de escenas del video semanal: el contrato entre el Editor y el Montaje."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["titular", "cifra", "grafico", "tarjeta", "porcentaje", "linea", "cierre"]
KINDS = ("titular", "cifra", "grafico", "tarjeta", "porcentaje", "linea", "cierre")
MAX_ON_SCREEN = 90
MIN_WORDS = 350
MAX_WORDS = 1200
MAX_SHORT_WORDS = 230
_FENCE_RE = re.compile(r"^\s*```\w*\s*|\s*```\s*$")


class SceneError(ValueError):
    """El guion de escenas no cumple el esquema."""


@dataclass
class Scene:
    id: str
    kind: Kind
    narration: str
    on_screen: str
    source: str | None = None
    value: str | None = None
    chart: list[tuple[str, float]] | None = None
    timeline: list[tuple[str, str]] | None = None
    short: bool = False


@dataclass
class SceneScript:
    title: str
    scenes: list[Scene]


def _words(text: str) -> int:
    return len(text.split())


def _parse_scene(d: dict, i: int) -> Scene:
    if not isinstance(d, dict):
        raise SceneError(f"escena {i}: debe ser un objeto")
    sid = str(d.get("id") or f"s{i}")
    kind = d.get("kind")
    if kind not in KINDS:
        raise SceneError(f"{sid}: kind inválido {kind!r} (use {', '.join(KINDS)})")
    narration = str(d.get("narration") or "").strip()
    if not narration:
        raise SceneError(f"{sid}: narration vacía")
    on_screen = str(d.get("on_screen") or "").strip()
    if len(on_screen) > MAX_ON_SCREEN:
        raise SceneError(f"{sid}: on_screen de {len(on_screen)} caracteres (máximo {MAX_ON_SCREEN})")
    value = d.get("value")
    value = None if value is None or value == "" else str(value)
    chart = timeline = None
    if kind == "cifra" and not value:
        raise SceneError(f"{sid}: una escena cifra exige value")
    if kind == "porcentaje":
        try:
            ok = value is not None and 0 <= float(value.replace(",", ".")) <= 100
        except ValueError:
            ok = False
        if not ok:
            raise SceneError(f"{sid}: value de porcentaje debe ser un número entre 0 y 100")
    if kind == "grafico":
        try:
            chart = [(str(c["label"]), float(c["value"])) for c in (d.get("chart") or [])]
        except (KeyError, TypeError, ValueError):
            raise SceneError(f"{sid}: chart mal formado (use [{{label, value}}])") from None
        if not 2 <= len(chart) <= 6 or any(v <= 0 for _, v in chart):
            raise SceneError(f"{sid}: chart necesita de 2 a 6 puntos con valores > 0")
    if kind == "linea":
        try:
            timeline = [(str(t["when"]), str(t["label"])) for t in (d.get("timeline") or [])]
        except (KeyError, TypeError):
            raise SceneError(f"{sid}: timeline mal formado (use [{{when, label}}])") from None
        if not 2 <= len(timeline) <= 4:
            raise SceneError(f"{sid}: timeline necesita de 2 a 4 hitos")
    source = d.get("source")
    return Scene(id=sid, kind=kind, narration=narration, on_screen=on_screen,
                 source=str(source) if source else None, value=value, chart=chart,
                 timeline=timeline, short=bool(d.get("short")))


def short_scenes(script: SceneScript) -> list[Scene]:
    """Escenas marcadas ``short`` (en orden) más el cierre, que siempre va."""
    return [s for s in script.scenes if s.short or s.kind == "cierre"]


def parse_scene_script(raw: str) -> SceneScript:
    try:
        data = json.loads(_FENCE_RE.sub("", raw.strip()))
    except json.JSONDecodeError as exc:
        raise SceneError(f"JSON inválido: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise SceneError("el JSON debe tener 'title' y una lista 'scenes'")
    scenes = [_parse_scene(d, i) for i, d in enumerate(data["scenes"], 1)]
    ids = [s.id for s in scenes]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise SceneError("ids duplicados: " + ", ".join(dup))
    script = SceneScript(title=str(data.get("title") or "").strip(), scenes=scenes)
    if not scenes or scenes[-1].kind != "cierre":
        raise SceneError("la última escena debe ser de tipo cierre")
    if not any(s.short for s in scenes):
        raise SceneError("marca al menos una escena con short: true")
    total = sum(_words(s.narration) for s in scenes)
    if not MIN_WORDS <= total <= MAX_WORDS:
        raise SceneError(f"narración de {total} palabras (debe estar entre {MIN_WORDS} y {MAX_WORDS})")
    short_words = sum(_words(s.narration) for s in short_scenes(script))
    if short_words > MAX_SHORT_WORDS:
        raise SceneError(f"las escenas short suman {short_words} palabras (máximo {MAX_SHORT_WORDS})")
    return script


def scene_texts(script: SceneScript) -> str:
    """Todo el texto visible u hablado de las escenas (lo que revisa el chequeo de cifras)."""
    parts: list[str] = []
    for s in script.scenes:
        parts += [s.narration, s.on_screen, s.value or ""]
        parts += [f"{label} {v:g}" for label, v in (s.chart or [])]
        parts += [f"{when} {label}" for when, label in (s.timeline or [])]
    return "\n".join(p for p in parts if p)
