"""Genera muestras de voz en samples/<proveedor>-<voz>.mp3 para elegir proveedor.

Uso: OPENROUTER_API_KEY=... OPENAI_API_KEY=... ELEVENLABS_API_KEY=... python scripts/make_voice_samples.py
Sin claves no hace nada (ni llama a la red). OpenRouter: modelo por SAMPLE_OPENROUTER_MODEL
(por defecto el de radio.tts) y voces por SAMPLE_OPENROUTER_VOICES; si no se definen, se leen del
listado público de OpenRouter (supported_voices) las primeras voces en español del modelo.
Voces por variable opcional: SAMPLE_OPENAI_VOICES="alloy,nova" y
SAMPLE_ELEVENLABS_VOICES="<voice_id>,<voice_id>" (ElevenLabs requiere voice_id).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from radio.tts import (ElevenLabsTts, OPENROUTER_DEFAULT_MODEL, OpenAITts,  # noqa: E402
                       OpenRouterTts, synthesize)

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

MODELS_URL = "https://openrouter.ai/api/v1/models?output_modalities=speech"


def openrouter_voices(model: str, limit: int = 3) -> list[str]:
    """Voces en español del modelo, leídas de ``supported_voices`` del listado público."""
    try:
        data = httpx.get(MODELS_URL, timeout=30).json()["data"]
    except Exception as exc:
        print(f"no se pudo leer el listado de voces de OpenRouter ({type(exc).__name__})")
        return []
    voices = next((m.get("supported_voices") or [] for m in data if m.get("id") == model), [])
    spanish = [v for v in voices if "es-" in v or v.startswith("es_") or "_es" in v]
    return spanish[:limit]


PROVIDERS = [
    ("openrouter", "OPENROUTER_API_KEY", None, "SAMPLE_OPENROUTER_VOICES", ""),
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
        model = os.environ.get("SAMPLE_OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL)
        voices = [v.strip() for v in os.environ.get(voices_var, default_voices).split(",") if v.strip()]
        if name == "openrouter" and not voices:
            voices = openrouter_voices(model)
        if not voices:
            skipped.append(f"{name} (defina {voices_var})")
            continue
        for voice in voices:
            tts = OpenRouterTts(key, voice, model) if name == "openrouter" else cls(key, voice)
            audio = synthesize(SAMPLE_TEXT, tts)
            safe = voice.replace(":", "_").replace("/", "_")
            path = OUT_DIR / f"{name}-{safe}.mp3"
            path.write_bytes(audio)
            print(f"escrito {path}")
    for s in skipped:
        print(f"omitido: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
