import json
import math
from datetime import date

from radio.video.manifest import FPS, TAIL_S, build_manifest, week_label
from radio.video.scenes import Scene, SceneScript
from radio.video.voice import SceneAudio


def make():
    scenes = [
        Scene(id="s1", kind="titular", narration="a", on_screen="Uno", short=True),
        Scene(id="s2", kind="cifra", narration="b", on_screen="días", value="11", source="Fast Company"),
        Scene(id="s3", kind="grafico", narration="c", on_screen="g", chart=[("A", 3.0), ("B", 5.0)]),
        Scene(id="s4", kind="linea", narration="d", on_screen="l",
              timeline=[("Día 0", "x"), ("Día 11", "y")], short=True),
        Scene(id="s5", kind="porcentaje", narration="e", on_screen="p", value="50"),
        Scene(id="s6", kind="cierre", narration="f", on_screen="Fin"),
    ]
    audios = [SceneAudio(s.id, b"\xff\xfb" + s.id.encode(), 2.0 + i * 0.1)
              for i, s in enumerate(scenes)]
    return SceneScript("Titulo", scenes), audios


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_horizontal_has_all_scenes(tmp_path):
    script, audios = make()
    p = build_manifest(script, audios, tmp_path, vertical=False, week_label="17–23 de noviembre de 2026")
    data = load(p)
    assert p == tmp_path / "props.json"
    assert data["fps"] == FPS == 30 and data["title"] == "Titulo"
    assert data["weekLabel"] == "17–23 de noviembre de 2026"
    assert [s["id"] for s in data["scenes"]] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    s2 = data["scenes"][1]
    assert s2["kind"] == "cifra" and s2["value"] == "11" and s2["onScreen"] == "días"
    assert s2["source"] == "Fast Company" and s2["chart"] is None and s2["timeline"] is None
    assert data["scenes"][2]["chart"] == [{"label": "A", "value": 3.0}, {"label": "B", "value": 5.0}]
    assert data["scenes"][3]["timeline"] == [{"when": "Día 0", "label": "x"},
                                             {"when": "Día 11", "label": "y"}]


def test_manifest_vertical_only_short_and_closing(tmp_path):
    script, audios = make()
    data = load(build_manifest(script, audios, tmp_path, vertical=True, week_label="x"))
    assert [s["id"] for s in data["scenes"]] == ["s1", "s4", "s6"]


def test_duration_frames_include_tail(tmp_path):
    script, audios = make()
    data = load(build_manifest(script, audios, tmp_path, vertical=False, week_label="x"))
    assert TAIL_S == 0.5
    assert data["scenes"][0]["durationFrames"] == math.ceil((2.0 + 0.5) * 30)
    assert data["scenes"][1]["durationFrames"] == math.ceil((2.1 + 0.5) * 30)


def test_audio_files_written_next_to_props(tmp_path):
    script, audios = make()
    data = load(build_manifest(script, audios, tmp_path, vertical=True, week_label="x"))
    for s in data["scenes"]:
        assert s["audio"] == f"audio/{s['id']}.mp3"
        assert (tmp_path / s["audio"]).read_bytes().startswith(b"\xff\xfb")
    assert not (tmp_path / "audio" / "s2.mp3").exists()


def test_week_label_same_month():
    days = [date(2026, 11, 17) + (date(2026, 11, 18) - date(2026, 11, 17)) * i for i in range(7)]
    assert week_label(days) == "17–23 de noviembre de 2026"


def test_week_label_crossing_month():
    days = [date(2026, 11, 28), date(2026, 11, 30), date(2026, 12, 4)]
    assert week_label(days) == "28 de noviembre – 4 de diciembre de 2026"


def test_week_label_crossing_year():
    assert week_label([date(2026, 12, 30), date(2027, 1, 3)]) == \
        "30 de diciembre de 2026 – 3 de enero de 2027"
