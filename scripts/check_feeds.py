"""Diagnóstico de feeds: úsalo una vez antes de la primera noche.

Uso: python scripts/check_feeds.py            (lee config.toml del directorio actual)

Para cada feed imprime: estado (ok/error), nº de entradas, nº de entradas de las últimas
36 h y, para hasta 2 entradas recientes, si se puede extraer el cuerpo y cuánto mide.
No usa claves ni escribe nada; solo hace peticiones GET con timeout corto.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser  # noqa: E402
import httpx  # noqa: E402

from radio.config import load_config  # noqa: E402
from radio.sources import USER_AGENT, _extract_body, _published  # noqa: E402

TIMEOUT = 10.0
WINDOW = timedelta(hours=36)
SAMPLE_BODIES = 2


def check_feed(client, url: str, since: datetime) -> tuple[bool, str]:
    """Devuelve (ok, informe de una o varias líneas) para un feed."""
    try:
        resp = client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
    except Exception as exc:
        return False, f"error  {url}\n    {type(exc).__name__}: {exc}"
    entries = list(parsed.entries)
    if parsed.get("bozo") and not entries:
        return False, f"error  {url}\n    XML mal formado"
    recent = []
    for e in entries:
        pub = _published(e)
        if pub is not None and pub >= since and e.get("link"):
            recent.append(e)
    lines = [f"{'ok   ' if entries else 'error'}  {url}",
             f"    entradas: {len(entries)}  últimas 36 h: {len(recent)}"
             + ("" if entries else "  (0 entradas: contaría como feed fallido)")]
    for e in recent[:SAMPLE_BODIES]:
        body = _extract_body(client, e["link"])
        state = f"cuerpo {len(body)} caracteres" if body else "SIN cuerpo (solo titular y resumen)"
        lines.append(f"    - {e.get('title', '')[:60]!r}: {state}")
    return bool(entries), "\n".join(lines)


def main() -> int:
    config = load_config()
    since = datetime.now(timezone.utc) - WINDOW
    failed = 0
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        for url in config.feeds:
            ok, report = check_feed(client, url, since)
            failed += not ok
            print(report)
    print(f"\n{len(config.feeds) - failed}/{len(config.feeds)} feeds ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
