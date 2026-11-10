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
MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 16


def test_openrouter_request_shape_openai_model_sends_instructions():
    client, seen = _client(body=MP3)
    tts = OpenRouterTts(KEY, "alloy", model="openai/gpt-4o-mini-tts-2025-12-15", client=client)
    assert tts.max_chars == 2500
    assert tts.speak("Hola mundo.") == MP3
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == "https://openrouter.ai/api/v1/audio/speech"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(req.content) == {
        "model": "openai/gpt-4o-mini-tts-2025-12-15", "input": "Hola mundo.",
        "voice": "alloy", "response_format": "mp3", "instructions": OPENAI_INSTRUCTIONS}


def test_openrouter_default_model_omits_unsupported_instructions():
    client, seen = _client(body=MP3)
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


def _resp_client(make):
    seen = []

    def handler(req):
        seen.append(req)
        return make(len(seen))
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


@pytest.mark.parametrize("resp", [
    httpx.Response(200, json={"error": {"message": "nope"}}),
    httpx.Response(200, content=b"<html>oops</html>", headers={"content-type": "audio/mpeg"}),
    httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}),
    httpx.Response(200, content=b"\xff\xfb\x90\x00", headers={"content-type": "text/plain"}),
    httpx.Response(200, content=b'{"a":1}', headers={"content-type": "audio/mpeg"}),
    httpx.Response(200, content=b"RIFF\x00\x00WAVEdata", headers={"content-type": "audio/wav"}),
    httpx.Response(200, content=b"\x00\x01\x02\x03" * 8),
], ids=["json", "html", "empty", "text-ct", "brace", "wav", "garbage"])
def test_openrouter_rejects_non_mp3_2xx(resp):
    client, _ = _resp_client(lambda n: resp)
    with pytest.raises(TtsError) as ei:
        OpenRouterTts(KEY, "v", client=client, sleep=lambda s: None).speak("x")
    assert KEY not in str(ei.value) and len(str(ei.value)) < 400


def test_openrouter_error_json_body_message_is_shown_truncated():
    client, _ = _resp_client(lambda n: httpx.Response(200, json={"error": "x" * 1000}))
    with pytest.raises(TtsError) as ei:
        OpenRouterTts(KEY, "v", client=client, sleep=lambda s: None).speak("x")
    assert "x" * 201 not in str(ei.value)


@pytest.mark.parametrize("body", [b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 8,
                                  b"\xff\xfb\x90\x00" + b"\x00" * 8,
                                  b"\xff\xf3\x40\x00" + b"\x00" * 8])
def test_openrouter_accepts_valid_mp3(body):
    client, _ = _resp_client(lambda n: httpx.Response(200, content=body,
                                                      headers={"content-type": "audio/mpeg"}))
    assert OpenRouterTts(KEY, "v", client=client, sleep=lambda s: None).speak("x") == body


# --- reintentos ---
def _flaky(statuses, ok_body=MP3):
    def make(n):
        st = statuses[min(n - 1, len(statuses) - 1)]
        return httpx.Response(st, content=ok_body if st == 200 else b"err")
    return _resp_client(make)


def test_openrouter_tts_retries_503_then_succeeds():
    client, seen = _flaky([503, 200])
    sleeps = []
    tts = OpenRouterTts(KEY, "v", client=client, sleep=sleeps.append)
    assert tts.speak("x") == MP3
    assert len(seen) == 2 and sleeps == [0.5]


def test_openrouter_tts_gives_up_after_three_attempts_without_leak():
    client, seen = _flaky([429])
    sleeps = []
    with pytest.raises(TtsError, match="429") as ei:
        OpenRouterTts(KEY, "v", client=client, sleep=sleeps.append).speak("x")
    assert len(seen) == 3 and sleeps == [0.5, 2.0] and KEY not in str(ei.value)


def test_openrouter_tts_no_retry_on_401():
    client, seen = _flaky([401])
    with pytest.raises(TtsError, match="401"):
        OpenRouterTts(KEY, "v", client=client, sleep=lambda s: None).speak("x")
    assert len(seen) == 1


def test_openrouter_tts_retries_transport_error():
    def handler(req):
        handler.n += 1
        if handler.n == 1:
            raise httpx.ReadTimeout("slow " + KEY)
        return httpx.Response(200, content=MP3)
    handler.n = 0
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert OpenRouterTts(KEY, "v", client=client, sleep=lambda s: None).speak("x") == MP3
    assert handler.n == 2


@pytest.mark.parametrize("cls", [OpenAITts, ElevenLabsTts])
def test_other_tts_retry_503_then_ok_and_no_retry_401(cls):
    client, seen = _flaky([503, 200], ok_body=b"MP3DATA")
    assert cls("k", "v", client=client, sleep=lambda s: None).speak("x") == b"MP3DATA"
    assert len(seen) == 2
    client, seen = _flaky([401])
    with pytest.raises(httpx.HTTPStatusError):
        cls("k", "v", client=client, sleep=lambda s: None).speak("x")
    assert len(seen) == 1
