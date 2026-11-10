import re

from radio.tts import split_text, synthesize


def _normalize(text: str) -> str:
    return " ".join(text.split())


LONG = " ".join(f"Esta es la oración número {i} del guion de hoy." for i in range(200))


def test_split_text_respects_limit_and_sentences():
    text = "Primera oración corta. Segunda oración un poco más larga.\n\nTercera en otro párrafo. Cuarta."
    chunks = split_text(text, 60)
    assert all(len(c) <= 60 for c in chunks)
    assert len(chunks) > 1
    # nunca a mitad de oración: cada trozo termina en fin de oración
    assert all(re.search(r"[.!?…]$", c) for c in chunks)
    assert " ".join(chunks) == _normalize(text)


def test_split_text_long_script_loses_nothing():
    chunks = split_text(LONG, 500)
    assert all(len(c) <= 500 for c in chunks)
    assert " ".join(chunks) == _normalize(LONG)


def test_split_text_oversized_sentence_splits_at_whitespace():
    sentence = " ".join(f"palabra{i}" for i in range(100)) + "."
    chunks = split_text(sentence, 50)
    assert all(len(c) <= 50 for c in chunks)
    assert " ".join(chunks) == _normalize(sentence)


def test_split_text_empty():
    assert split_text("  \n ", 100) == []


class FakeProvider:
    max_chars = 500

    def __init__(self):
        self.calls: list[str] = []

    def speak(self, chunk: str) -> bytes:
        self.calls.append(chunk)
        return f"[{len(self.calls)}]".encode()


def test_synthesize_concatenates_chunks_in_order():
    p = FakeProvider()
    audio = synthesize(LONG, p)
    assert len(p.calls) > 1
    assert " ".join(p.calls) == _normalize(LONG)
    assert audio == b"".join(f"[{i}]".encode() for i in range(1, len(p.calls) + 1))


# --- adaptadores de proveedor (sin red: transporte httpx falso) ---
import json

import httpx
import pytest

from radio.config import Config
from radio.tts import (ElevenLabsTts, OpenAITts, OpenRouterTts, TtsError,
                       provider_from_config, OPENROUTER_DEFAULT_MODEL, OPENROUTER_DEFAULT_VOICE)

OPENAI_INSTRUCTIONS = ("Habla en español latinoamericano neutro, con tono natural, cálido y claro "
                       "de radio matutina; ritmo pausado")


def _client(status=200, body=b"MP3DATA"):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_openai_request_shape():
    client, seen = _client()
    tts = OpenAITts(api_key="k-test", voice="alloy", client=client)
    assert tts.max_chars == 4000
    assert tts.speak("Hola mundo.") == b"MP3DATA"
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://api.openai.com/v1/audio/speech"
    assert req.headers["authorization"] == "Bearer k-test"
    assert json.loads(req.content) == {
        "model": "gpt-4o-mini-tts", "input": "Hola mundo.",
        "voice": "alloy", "response_format": "mp3",
        "instructions": OPENAI_INSTRUCTIONS,
    }


def test_elevenlabs_request_shape():
    client, seen = _client()
    tts = ElevenLabsTts(api_key="k-test", voice="VOICE123", client=client)
    assert tts.max_chars == 4500
    assert tts.speak("Hola mundo.") == b"MP3DATA"
    req = seen[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/text-to-speech/VOICE123"
    assert req.url.host == "api.elevenlabs.io"
    assert req.url.params["output_format"] == "mp3_44100_128"
    assert req.headers["xi-api-key"] == "k-test"
    assert json.loads(req.content) == {"text": "Hola mundo.", "model_id": "eleven_multilingual_v2"}


@pytest.mark.parametrize("cls", [OpenAITts, ElevenLabsTts])
def test_http_error_raises(cls):
    client, _ = _client(status=401, body=b"nope")
    with pytest.raises(httpx.HTTPStatusError):
        cls(api_key="k", voice="v", client=client).speak("x")


def test_provider_from_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k2")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k3")
    assert isinstance(provider_from_config(Config(tts_provider="openrouter")), OpenRouterTts)
    assert isinstance(provider_from_config(Config(tts_provider="openai", tts_voice="alloy")), OpenAITts)
    assert isinstance(provider_from_config(Config(tts_provider="elevenlabs", tts_voice="v")), ElevenLabsTts)


def test_provider_from_config_openai_default_voice(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    assert provider_from_config(Config(tts_provider="openai")).voice == "alloy"


def test_provider_from_config_errors(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        provider_from_config(Config(tts_provider="openrouter"))
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        provider_from_config(Config(tts_provider="openai"))
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        provider_from_config(Config(tts_provider="elevenlabs", tts_voice="v"))
    with pytest.raises(ValueError, match="foo"):
        provider_from_config(Config(tts_provider="foo"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    with pytest.raises(ValueError, match="tts_voice"):
        provider_from_config(Config(tts_provider="elevenlabs", tts_voice=""))


# --- OpenRouter ---
KEY = "sk-or-SECRET123"


def test_openrouter_request_shape_openai_model_sends_instructions():
    client, seen = _client()
    tts = OpenRouterTts(KEY, "alloy", model="openai/gpt-4o-mini-tts-2025-12-15", client=client)
    assert tts.max_chars == 4000
    assert tts.speak("Hola mundo.") == b"MP3DATA"
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://openrouter.ai/api/v1/audio/speech"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(req.content) == {
        "model": "openai/gpt-4o-mini-tts-2025-12-15", "input": "Hola mundo.",
        "voice": "alloy", "response_format": "mp3", "instructions": OPENAI_INSTRUCTIONS}


def test_openrouter_default_model_omits_unsupported_instructions():
    client, seen = _client()
    OpenRouterTts(KEY, OPENROUTER_DEFAULT_VOICE, client=client).speak("Hola.")
    body = json.loads(seen[0].content)
    assert body["model"] == OPENROUTER_DEFAULT_MODEL
    assert body["voice"] == OPENROUTER_DEFAULT_VOICE
    assert body["response_format"] == "mp3" and "instructions" not in body


def test_openrouter_error_status_does_not_leak_key():
    client, _ = _client(status=401, body=f"bad key {KEY}".encode())
    with pytest.raises(TtsError, match="401") as ei:
        OpenRouterTts(KEY, "v", client=client).speak("x")
    assert KEY not in str(ei.value)


def test_openrouter_provider_defaults_and_overrides(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    p = provider_from_config(Config(tts_provider="openrouter"))
    assert (p.model, p.voice) == (OPENROUTER_DEFAULT_MODEL, OPENROUTER_DEFAULT_VOICE)
    p = provider_from_config(Config(tts_provider="openrouter", tts_model="openai/x-tts", tts_voice="nova"))
    assert (p.model, p.voice) == ("openai/x-tts", "nova")
    with pytest.raises(ValueError, match="tts_voice"):
        provider_from_config(Config(tts_provider="openrouter", tts_model="openai/x-tts"))
