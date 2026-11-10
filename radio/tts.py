"""Texto a voz: trocea el guion, sintetiza cada trozo y une el MP3."""
from __future__ import annotations

import os
import re
import time
from typing import Callable, Protocol

import httpx

from radio.config import Config
from radio.http_retry import post_with_retry


class TtsProvider(Protocol):
    max_chars: int

    def speak(self, chunk: str) -> bytes: ...


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _split_long(sentence: str, max_chars: int) -> list[str]:
    """Parte una oración demasiado larga en el último espacio bajo el límite."""
    parts: list[str] = []
    rest = sentence
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars + 1)
        if cut <= 0:  # sin espacios: corte duro
            cut = max_chars
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def split_text(text: str, max_chars: int) -> list[str]:
    """Trozos de <= max_chars, cortando en fin de oración (o en espacio si una
    oración sola excede el límite). Los espacios se normalizan a uno."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(normalized):
        pieces = [sentence] if len(sentence) <= max_chars else _split_long(sentence, max_chars)
        for piece in pieces:
            if current and len(current) + 1 + len(piece) <= max_chars:
                current += " " + piece
            else:
                if current:
                    chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def synthesize(text: str, provider: TtsProvider) -> bytes:
    """MP3 completo. Concatenar los bytes de los trozos es válido para MP3:
    los frames son independientes, y los reproductores los encadenan."""
    return b"".join(provider.speak(c) for c in split_text(text, provider.max_chars))


TIMEOUT = 120.0


class OpenAITts:
    max_chars = 4000
    url = "https://api.openai.com/v1/audio/speech"
    model = "gpt-4o-mini-tts"
    instructions = ("Habla en español latinoamericano neutro, con tono natural, cálido y "
                    "claro de radio matutina; ritmo pausado")

    def __init__(self, api_key: str, voice: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key
        self.voice = voice
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.sleep = sleep

    def speak(self, chunk: str) -> bytes:
        resp = post_with_retry(
            self.client, self.url, sleep=self.sleep,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": chunk, "voice": self.voice,
                  "response_format": "mp3", "instructions": self.instructions},
        )
        resp.raise_for_status()
        return resp.content


class TtsError(Exception):
    """Fallo del proveedor de voz. El mensaje nunca contiene la clave."""


# Modelo y voz por defecto, leídos del listado público de OpenRouter
# (GET /api/v1/models?output_modalities=speech). Hay que escuchar el resultado.
OPENROUTER_DEFAULT_MODEL = "microsoft/mai-voice-2.1-flash"
OPENROUTER_DEFAULT_VOICE = "es-MX-Valeria:MAI-Voice-2.1-Flash"
# Según la documentación de OpenRouter, `instructions` solo lo usan estos proveedores.
_INSTRUCTIONS_PREFIXES = ("openai/", "google/", "fish-audio/")


def _looks_like_mp3(data: bytes) -> bool:
    if data[:3] == b"ID3":
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


class OpenRouterTts:
    # Conservador: el límite por petición del modelo por defecto no está verificado.
    max_chars = 2500
    url = "https://openrouter.ai/api/v1/audio/speech"
    instructions = OpenAITts.instructions

    def __init__(self, api_key: str, voice: str, model: str = OPENROUTER_DEFAULT_MODEL,
                 client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key
        self.voice = voice
        self.model = model
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.sleep = sleep

    def _clean(self, text: str) -> str:
        return text.replace(self.api_key, "[REDACTED]") if self.api_key else text

    def speak(self, chunk: str) -> bytes:
        body = {"model": self.model, "input": chunk, "voice": self.voice,
                "response_format": "mp3"}
        if self.model.startswith(_INSTRUCTIONS_PREFIXES):
            body["instructions"] = self.instructions
        try:
            resp = post_with_retry(
                self.client, self.url, sleep=self.sleep,
                headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
        except httpx.HTTPError as exc:
            raise TtsError(f"OpenRouter TTS: fallo de red ({type(exc).__name__})") from None
        if not resp.is_success:
            detail = self._clean(resp.text[:300])
            raise TtsError(f"OpenRouter TTS devolvió HTTP {resp.status_code}: {detail}")
        data = resp.content
        ctype = resp.headers.get("content-type", "").lower()
        if (not data or "json" in ctype or "text" in ctype or data[:1] in (b"{", b"<")
                or not _looks_like_mp3(data)):
            try:
                preview = self._clean(data[:200].decode("utf-8"))
            except UnicodeDecodeError:
                preview = ""
            msg = (f"OpenRouter TTS devolvió HTTP {resp.status_code} pero no un MP3 válido "
                   f"({len(data)} bytes, content-type {ctype or 'desconocido'!r})")
            raise TtsError(msg + (f": {preview}" if preview else ""))
        return data


class ElevenLabsTts:
    max_chars = 4500
    base_url = "https://api.elevenlabs.io/v1/text-to-speech"
    model_id = "eleven_multilingual_v2"

    def __init__(self, api_key: str, voice: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key
        self.voice = voice  # voice_id
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.sleep = sleep

    def speak(self, chunk: str) -> bytes:
        resp = post_with_retry(
            self.client, f"{self.base_url}/{self.voice}", sleep=self.sleep,
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.api_key},
            json={"text": chunk, "model_id": self.model_id},
        )
        resp.raise_for_status()
        return resp.content


OPENAI_DEFAULT_VOICE = "alloy"


def _require_key(env_var: str) -> str:
    key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(f"Falta la variable de entorno {env_var} para el proveedor TTS")
    return key


def provider_from_config(config: Config) -> TtsProvider:
    name = config.tts_provider
    if name == "openrouter":
        key = _require_key("OPENROUTER_API_KEY")
        model = config.tts_model or OPENROUTER_DEFAULT_MODEL
        voice = config.tts_voice
        if not voice:
            if model != OPENROUTER_DEFAULT_MODEL:
                raise ValueError(f"tts_voice es obligatorio con tts_model = {model!r} "
                                 "(las voces dependen del modelo; ver supported_voices)")
            voice = OPENROUTER_DEFAULT_VOICE
        return OpenRouterTts(key, voice, model)
    if name == "openai":
        return OpenAITts(_require_key("OPENAI_API_KEY"), config.tts_voice or OPENAI_DEFAULT_VOICE)
    if name == "elevenlabs":
        key = _require_key("ELEVENLABS_API_KEY")
        if not config.tts_voice:
            raise ValueError("tts_voice (voice_id de ElevenLabs) es obligatorio con tts_provider = 'elevenlabs'")
        return ElevenLabsTts(key, config.tts_voice)
    raise ValueError(f"tts_provider desconocido: {name!r} (use 'openrouter', 'openai' o 'elevenlabs')")
