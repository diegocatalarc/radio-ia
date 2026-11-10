"""POST con reintentos: hasta 3 intentos con espera 0,5 s y 2 s."""
from __future__ import annotations

import time
from typing import Callable

import httpx

BACKOFF_S = (0.5, 2.0)
RETRY_STATUS = {408, 429}


def _retryable_status(code: int) -> bool:
    return code in RETRY_STATUS or code >= 500


def post_with_retry(client: httpx.Client, url: str, *,
                    sleep: Callable[[float], None] = time.sleep, **kwargs) -> httpx.Response:
    """Reintenta ante 408/429/5xx y ``httpx.TransportError`` (incluye timeouts); nunca ante
    otros 4xx. Tras el último intento devuelve la última respuesta o relanza el error de red."""
    attempts = len(BACKOFF_S) + 1
    for i in range(attempts):
        last = i == attempts - 1
        try:
            resp = client.post(url, **kwargs)
        except httpx.TransportError:
            if last:
                raise
        else:
            if last or not _retryable_status(resp.status_code):
                return resp
        sleep(BACKOFF_S[i])
    raise AssertionError("unreachable")
