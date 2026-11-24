"""Voz por escena: una locución por escena; su duración real fija la duración de la escena."""
from __future__ import annotations

from dataclasses import dataclass

from radio.audio import mp3_duration
from radio.tts import TtsProvider, synthesize
from radio.video.scenes import SceneScript


class VoiceError(Exception):
    """La voz devolvió audio vacío o inutilizable para una escena."""


@dataclass
class SceneAudio:
    scene_id: str
    mp3: bytes
    duration_s: float


def narrate(script: SceneScript, tts: TtsProvider) -> list[SceneAudio]:
    """Una locución por escena, en orden. Si cualquiera falla no se devuelve nada."""
    out: list[SceneAudio] = []
    for scene in script.scenes:
        data = synthesize(scene.narration, tts)
        duration = mp3_duration(data)
        if not data or duration <= 0:
            raise VoiceError(f"{scene.id}: la voz devolvió audio vacío")
        out.append(SceneAudio(scene_id=scene.id, mp3=data, duration_s=duration))
    return out
