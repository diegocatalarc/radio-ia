"""Añade una corrección a ``state.json``; el próximo episodio la mencionará una vez.

Uso: ``python -m radio.correct "texto de la corrección" [--state state.json]``
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from radio.state import State


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text")
    ap.add_argument("--state", default="state.json")
    args = ap.parse_args(argv)
    text = args.text.strip()
    if not text:
        print("La corrección está vacía", file=sys.stderr)
        return 1
    path = Path(args.state)
    state = State.load(path)
    state.add_correction(text)
    state.save(path)
    print(f"Corrección guardada en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
