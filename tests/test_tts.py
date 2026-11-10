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
