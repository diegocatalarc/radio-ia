import pytest

from radio.audio import mp3_duration
from radio.run import estimate_mp3_duration_s
from radio.video.scenes import Scene, SceneScript
from radio.video.voice import SceneAudio, VoiceError, narrate

FRAME = b"\xff\xfb\x90\x00"  # MPEG-1 Layer III, 128 kbps


def mp3(seconds):
    return FRAME + b"\x00" * (16000 * seconds - 4)


class FakeTts:
    max_chars = 4000

    def __init__(self, fail_on=None, empty_on=None):
        self.fail_on, self.empty_on, self.spoken = fail_on, empty_on, []

    def speak(self, chunk):
        self.spoken.append(chunk)
        if chunk == self.fail_on:
            raise RuntimeError("tts down")
        if chunk == self.empty_on:
            return b""
        return mp3(2)


def script(*texts):
    scenes = [Scene(id=f"s{i}", kind="titular", narration=t, on_screen="x")
              for i, t in enumerate(texts, 1)]
    return SceneScript(title="T", scenes=scenes)


def test_mp3_duration_is_float_and_matches_old_estimate():
    assert mp3_duration(mp3(5)) == pytest.approx(5.0, abs=0.01)
    assert estimate_mp3_duration_s(mp3(5)) == round(mp3_duration(mp3(5))) == 5
    assert mp3_duration(b"") == 0.0
    assert estimate_mp3_duration_s(b"") == 1


def test_narrate_one_audio_per_scene_in_order():
    tts = FakeTts()
    out = narrate(script("uno", "dos", "tres"), tts)
    assert [a.scene_id for a in out] == ["s1", "s2", "s3"]
    assert tts.spoken == ["uno", "dos", "tres"]
    assert all(isinstance(a, SceneAudio) and a.duration_s == pytest.approx(2.0, abs=0.01)
               for a in out)
    assert out[0].mp3.startswith(b"\xff\xfb")


def test_narrate_empty_audio_raises_voice_error_naming_scene():
    with pytest.raises(VoiceError, match="s2"):
        narrate(script("uno", "dos"), FakeTts(empty_on="dos"))


def test_narrate_provider_error_propagates_without_partial_result():
    with pytest.raises(RuntimeError, match="tts down"):
        narrate(script("uno", "dos"), FakeTts(fail_on="dos"))


def xing_mp3(frames, flags=3, total=None):
    # Cabecera MPEG-1 L3 estéreo 44,1 kHz, 32 bytes de relleno, etiqueta Xing con frames y bytes.
    body = b"\x00" * 200
    n = 4 + 32 + 4 + 4 + 4 + 4 + len(body)
    return (b"\xff\xfb\x90\x00" + b"\x00" * 32 + b"Xing" + flags.to_bytes(4, "big")
            + frames.to_bytes(4, "big") + (total or n).to_bytes(4, "big") + body)


def test_mp3_duration_uses_xing_frame_count_for_vbr():
    assert mp3_duration(xing_mp3(1000)) == pytest.approx(1000 * 1152 / 44100, abs=0.01)


def test_mp3_duration_counts_every_concatenated_chunk_with_xing():
    one = xing_mp3(1000)
    assert mp3_duration(one * 3) == pytest.approx(3 * 1000 * 1152 / 44100, abs=0.05)


def test_mp3_duration_falls_back_to_cbr_without_frames_and_bytes_flags():
    for flags in (0, 1, 2):
        data = xing_mp3(1000, flags=flags)
        assert mp3_duration(data) == pytest.approx(len(data) * 8 / 128000, abs=0.01)


def test_mp3_duration_of_real_vbr_fixture():
    from pathlib import Path
    data = Path("video/fixtures/audio/f1.mp3").read_bytes()
    assert mp3_duration(data) == pytest.approx(3.03, abs=0.05)
    assert mp3_duration(data * 3) == pytest.approx(3 * 3.03, abs=0.15)
