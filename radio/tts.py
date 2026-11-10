"""Texto a voz: trocea el guion, sintetiza cada trozo y une el MP3."""
from __future__ import annotations

import re
from typing import Protocol


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
