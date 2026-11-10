"""Genera muestras de voz en samples/<proveedor>-<voz>.mp3 para elegir proveedor.

Uso: OPENAI_API_KEY=... ELEVENLABS_API_KEY=... python scripts/make_voice_samples.py
Voces por variable opcional: SAMPLE_OPENAI_VOICES="alloy,nova" y
SAMPLE_ELEVENLABS_VOICES="<voice_id>,<voice_id>" (ElevenLabs requiere voice_id).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radio.tts import ElevenLabsTts, OpenAITts, synthesize  # noqa: E402

SAMPLE_TEXT = (
    "Buenos días, esto es Radio IA. Hoy la inteligencia artificial ya no es solo una promesa "
    "de laboratorio: las empresas la usan para escribir código, atender clientes y analizar "
    "contratos, y los mercados lo notan. Los analistas debaten si esta ola elevará la "
    "productividad de toda la economía o si concentrará las ganancias en unas pocas compañías "
    "con acceso a chips y centros de datos. Mientras tanto, los gobiernos intentan decidir "
    "cuánto regular sin frenar la inversión, y los trabajadores se preguntan qué tareas "
    "cambiarán primero. Te lo contamos con calma, con cifras y con sus fuentes."
)

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"

PROVIDERS = [
    ("openai", "OPENAI_API_KEY", OpenAITts, "SAMPLE_OPENAI_VOICES", "alloy,nova,onyx"),
    ("elevenlabs", "ELEVENLABS_API_KEY", ElevenLabsTts, "SAMPLE_ELEVENLABS_VOICES", ""),
]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    skipped = []
    for name, key_var, cls, voices_var, default_voices in PROVIDERS:
        key = os.environ.get(key_var)
        if not key:
            skipped.append(f"{name} (falta {key_var})")
            continue
        voices = [v.strip() for v in os.environ.get(voices_var, default_voices).split(",") if v.strip()]
        if not voices:
            skipped.append(f"{name} (defina {voices_var} con voice_ids)")
            continue
        for voice in voices:
            audio = synthesize(SAMPLE_TEXT, cls(key, voice))
            path = OUT_DIR / f"{name}-{voice}.mp3"
            path.write_bytes(audio)
            print(f"escrito {path}")
    for s in skipped:
        print(f"omitido: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
