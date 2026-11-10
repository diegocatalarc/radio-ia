"""Interfaz mínima de LLM: ``complete(prompt, model=, max_tokens=) -> LlmReply``.

Adaptadores: OpenRouter (por defecto, vía httpx) y Anthropic (SDK, import perezoso).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

TIMEOUT = 180.0
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LlmError(Exception):
    """Fallo de la API del LLM. El mensaje nunca contiene la clave."""


@dataclass
class LlmReply:
    text: str
    stop: str  # "end" | "max_tokens" | "refusal" | "other"


class Llm(Protocol):
    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LlmReply: ...


_FINISH = {"stop": "end", "length": "max_tokens", "content_filter": "refusal"}


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
        return "".join(out)
    return ""


class OpenRouterLlm:
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def _clean(self, text: str) -> str:
        return text.replace(self.api_key, "[REDACTED]") if self.api_key else text

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LlmReply:
        try:
            resp = self.client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens})
        except httpx.HTTPError as exc:
            raise LlmError(f"OpenRouter: fallo de red ({type(exc).__name__})") from None
        try:
            data = resp.json()
        except ValueError:
            data = None
        err = data.get("error") if isinstance(data, dict) else None
        if err is not None or not resp.is_success:
            detail = ""
            if isinstance(err, dict):
                detail = str(err.get("message") or "")
            elif err:
                detail = str(err)
            msg = f"OpenRouter devolvió un error (HTTP {resp.status_code})"
            if detail:
                msg += f": {detail[:300]}"
            raise LlmError(self._clean(msg))
        if not isinstance(data, dict):
            raise LlmError("OpenRouter devolvió una respuesta que no es JSON")
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else {}
        if not isinstance(choice, dict):
            choice = {}
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return LlmReply(text=_text_of(content),
                        stop=_FINISH.get(choice.get("finish_reason"), "other"))


_ANTHROPIC_STOP = {"end_turn": "end", "stop_sequence": "end", "max_tokens": "max_tokens",
                   "refusal": "refusal"}


class AnthropicLlm:
    """Adaptador del SDK de Anthropic (dependencia opcional: ``pip install .[anthropic]``)."""

    def __init__(self, client=None):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ValueError("llm_provider = 'anthropic' requiere el paquete anthropic "
                                 "(pip install '.[anthropic]')") from exc
            client = anthropic.Anthropic()
        self.client = client

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LlmReply:
        resp = self.client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        text = ""
        for block in getattr(resp, "content", None) or []:
            t = getattr(block, "text", None)
            if isinstance(t, str) and t.strip():
                text = t
                break
        reason = getattr(resp, "stop_reason", None)
        return LlmReply(text=text, stop=_ANTHROPIC_STOP.get(reason, "other"))


def llm_from_config(config) -> Llm:
    name = config.llm_provider
    if name == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("Falta la variable de entorno OPENROUTER_API_KEY para el LLM")
        return OpenRouterLlm(key)
    if name == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("Falta la variable de entorno ANTHROPIC_API_KEY para el LLM")
        return AnthropicLlm()
    raise ValueError(f"llm_provider desconocido: {name!r} (use 'openrouter' o 'anthropic')")
