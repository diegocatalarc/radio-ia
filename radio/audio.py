"""Utilidades de audio MP3 sin dependencias."""
from __future__ import annotations

DEFAULT_BITRATE_BPS = 128_000

# MPEG1 Layer III bitrates (kbps) by header index.
_BITRATES_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
# MPEG-2 y MPEG-2.5 Layer III (kbps).
_BITRATES_MPEG2_KBPS = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]


def mp3_duration(data: bytes) -> float:
    """Duración estimada en segundos (float, 0.0 si no hay audio) sin dependencias.

    Salta una etiqueta ID3v2 si existe y lee la cabecera del primer frame MPEG Layer III
    (MPEG-1, MPEG-2 o MPEG-2.5; cada versión tiene su tabla de bitrates) para obtener el
    bitrate y calcula ``bytes * 8 / bitrate``. Es exacto para CBR (lo que producen OpenAI,
    ElevenLabs y normalmente Azure); si no hay cabecera válida se asume 128 kbps.
    """
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
               ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        pos = 10 + size
    bitrate = DEFAULT_BITRATE_BPS
    for i in range(pos, min(len(data) - 3, pos + 4096)):
        b1, b2, b3 = data[i], data[i + 1], data[i + 2]
        if b1 != 0xFF or (b2 & 0xE0) != 0xE0:
            continue
        version = (b2 >> 3) & 0x03   # 0 = MPEG-2.5, 1 = reservado, 2 = MPEG-2, 3 = MPEG-1
        layer = (b2 >> 1) & 0x03     # 1 = Layer III
        idx = b3 >> 4
        if version == 1 or layer != 1 or not 1 <= idx <= 14 or (b3 >> 2) & 0x03 == 3:
            continue
        table = _BITRATES_KBPS if version == 3 else _BITRATES_MPEG2_KBPS
        bitrate = table[idx] * 1000
        break
    return max(0, len(data) - pos) * 8 / bitrate
