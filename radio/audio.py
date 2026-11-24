"""Utilidades de audio MP3 sin dependencias."""
from __future__ import annotations

DEFAULT_BITRATE_BPS = 128_000

# MPEG1 Layer III bitrates (kbps) by header index.
_BITRATES_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
# MPEG-2 y MPEG-2.5 Layer III (kbps).
_BITRATES_MPEG2_KBPS = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
# Frecuencias de muestreo (Hz) por versión: 0 = MPEG-2.5, 2 = MPEG-2, 3 = MPEG-1.
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _xing_counts(data: bytes, frame_pos: int) -> tuple[int, int]:
    """(frames, bytes) de la etiqueta Xing/Info del primer frame, o (0, 0) si falta alguno."""
    window = data[frame_pos + 4: frame_pos + 4 + 64]
    for name in (b"Xing", b"Info"):
        j = window.find(name)
        if j < 0:
            continue
        flags = window[j + 4: j + 8]
        if len(flags) == 4 and flags[3] & 1 and flags[3] & 2 and len(window) >= j + 16:
            return (int.from_bytes(window[j + 8: j + 12], "big"),
                    int.from_bytes(window[j + 12: j + 16], "big"))
    return 0, 0


def mp3_duration(data: bytes) -> float:
    """Duración estimada en segundos (float, 0.0 si no hay audio) sin dependencias.

    Salta una etiqueta ID3v2 si existe y lee la cabecera del primer frame MPEG Layer III
    (MPEG-1, MPEG-2 o MPEG-2.5; cada versión tiene su tabla de bitrates) para obtener el
    bitrate y calcula ``bytes * 8 / bitrate``. Es exacto para CBR (lo que producen OpenAI,
    ElevenLabs y normalmente Azure); si no hay cabecera válida se asume 128 kbps. Si el primer
    frame lleva una etiqueta Xing/Info con el recuento de frames y de bytes (típico de VBR) se usa ese
    recuento, escalado por los bytes reales, que es exacto también para VBR y para trozos concatenados.
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
        frames, xing_bytes = _xing_counts(data, i)
        sr = _SAMPLE_RATES[version][(b3 >> 2) & 0x03]
        if frames and xing_bytes:
            # La etiqueta describe solo el primer stream; si hay varios MP3 concatenados
            # (``synthesize`` une trozos) se escala por los bytes reales.
            return frames * (1152 if version == 3 else 576) / sr * (len(data) - pos) / xing_bytes
        table = _BITRATES_KBPS if version == 3 else _BITRATES_MPEG2_KBPS
        bitrate = table[idx] * 1000
        break
    return max(0, len(data) - pos) * 8 / bitrate
