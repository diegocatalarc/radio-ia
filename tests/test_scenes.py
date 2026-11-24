import json

import pytest

from radio.video.scenes import SceneError, parse_scene_script, scene_texts, short_scenes


def words(n):
    return " ".join(["palabra"] * n)


def scene(i, kind="titular", narration=None, **kw):
    d = {"id": f"s{i}", "kind": kind, "narration": narration or words(60),
         "on_screen": "Texto", "value": None, "chart": None, "timeline": None,
         "source": None, "short": False}
    d.update(kw)
    return d


def script(scenes=None, **kw):
    scenes = scenes or [scene(1, short=True), scene(2), scene(3), scene(4), scene(5),
                        scene(6, short=True), scene(7, "cierre", short=True)]
    d = {"title": "Titulo", "thesis": "Tesis", "scenes": scenes}
    d.update(kw)
    return json.dumps(d)


def err(raw, match):
    with pytest.raises(SceneError, match=match):
        parse_scene_script(raw)


def test_parse_valid_script():
    s = parse_scene_script(script())
    assert s.title == "Titulo" and len(s.scenes) == 7
    assert s.scenes[0].short is True and s.scenes[-1].kind == "cierre"


def test_parse_accepts_json_fence():
    assert len(parse_scene_script("```json\n" + script() + "\n```").scenes) == 7


def test_parse_invalid_json_rejected():
    err("no es json", "JSON")


def test_on_screen_over_90_chars_rejected():
    sc = [scene(1, short=True, on_screen="x" * 91)] + [scene(i) for i in range(2, 7)] + \
         [scene(7, "cierre", short=True)]
    err(script(sc), "on_screen")


def test_chart_with_one_point_rejected():
    sc = [scene(1, "grafico", short=True, chart=[{"label": "a", "value": 1}])] + \
         [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    err(script(sc), "chart")


def test_chart_with_non_positive_value_rejected():
    ch = [{"label": "a", "value": 1}, {"label": "b", "value": 0}]
    sc = [scene(1, "grafico", short=True, chart=ch)] + [scene(i) for i in range(2, 7)] + \
         [scene(7, "cierre")]
    err(script(sc), "chart")


def test_cifra_without_value_rejected():
    sc = [scene(1, "cifra", short=True)] + [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    err(script(sc), "value")


def test_porcentaje_requires_number_between_0_and_100():
    base = [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    for bad in (None, "abc", 101, -1):
        err(script([scene(1, "porcentaje", short=True, value=bad)] + base), "value")
    ok = parse_scene_script(script([scene(1, "porcentaje", short=True, value=50)] + base))
    assert ok.scenes[0].value == "50"


def test_linea_requires_2_to_4_milestones():
    base = [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    one = [{"when": "Día 0", "label": "a"}]
    five = [{"when": f"Día {i}", "label": "a"} for i in range(5)]
    for bad in (None, one, five):
        err(script([scene(1, "linea", short=True, timeline=bad)] + base), "timeline")
    two = [{"when": "Día 0", "label": "a"}, {"when": "Día 11", "label": "b"}]
    ok = parse_scene_script(script([scene(1, "linea", short=True, timeline=two)] + base))
    assert ok.scenes[0].timeline == [("Día 0", "a"), ("Día 11", "b")]


def test_duplicate_ids_rejected():
    sc = [scene(1, short=True), scene(1)] + [scene(i) for i in range(3, 7)] + \
         [scene(7, "cierre", short=True)]
    err(script(sc), "duplicad")


def test_last_scene_must_be_cierre():
    sc = [scene(i, short=(i == 1)) for i in range(1, 8)]
    err(script(sc), "cierre")


def test_unknown_kind_rejected():
    sc = [scene(1, "video", short=True)] + [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    err(script(sc), "kind")


def test_at_least_one_short_required():
    sc = [scene(i) for i in range(1, 7)] + [scene(7, "cierre")]
    err(script(sc), "short")


def test_short_over_230_words_rejected():
    sc = [scene(1, short=True, narration=words(231))] + [scene(i) for i in range(2, 7)] + \
         [scene(7, "cierre")]
    err(script(sc), "230")


def test_total_words_out_of_range_rejected():
    small = [scene(1, short=True, narration=words(10)), scene(2, "cierre", narration=words(10))]
    err(script(small), "palabras")
    big = [scene(1, short=True, narration=words(200))] + \
          [scene(i, narration=words(200)) for i in range(2, 8)] + [scene(8, "cierre", narration=words(1))]
    err(script(big), "palabras")


def test_scene_texts_includes_value_chart_and_timeline():
    ch = [{"label": "Uno", "value": 3}, {"label": "Dos", "value": 5}]
    tl = [{"when": "Día 0", "label": "inicio"}, {"when": "Día 11", "label": "fin"}]
    sc = [scene(1, "cifra", short=True, value="11", on_screen="días"),
          scene(2, "grafico", chart=ch), scene(3, "linea", timeline=tl)] + \
         [scene(i) for i in range(4, 7)] + [scene(7, "cierre")]
    txt = scene_texts(parse_scene_script(script(sc)))
    for needle in ("11", "días", "Uno", "5", "Día 11", "fin"):
        assert needle in txt


def test_short_scenes_returns_short_flagged_in_order():
    s = parse_scene_script(script())
    assert [x.id for x in short_scenes(s)] == ["s1", "s6", "s7"]


def test_short_scenes_appends_closing_when_not_flagged():
    sc = [scene(1, short=True)] + [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]
    s = parse_scene_script(script(sc))
    assert [x.id for x in short_scenes(s)] == ["s1", "s7"]


BASE_TAIL = [scene(i) for i in range(2, 7)] + [scene(7, "cierre")]


def test_scene_id_must_be_a_safe_filename():
    for bad in ("../../evil", "a/b", "s 1", "x" * 33, "a.b"):
        err(script([scene(1, short=True, id=bad)] + BASE_TAIL), "id")


def test_cifra_value_needs_a_digit_and_max_10_chars():
    for bad in ("cuarenta mil", "1234567.8901"):
        err(script([scene(1, "cifra", short=True, value=bad)] + BASE_TAIL), "value")
    ok = parse_scene_script(script([scene(1, "cifra", short=True, value="US$ 20M")] + BASE_TAIL))
    assert ok.scenes[0].value == "US$ 20M"


def test_chart_values_must_be_finite():
    for bad in ("nan", "inf"):
        ch = [{"label": "a", "value": 1}, {"label": "b", "value": bad}]
        err(script([scene(1, "grafico", short=True, chart=ch)] + BASE_TAIL), "chart")


def test_overlong_labels_and_source_rejected():
    ch = [{"label": "x" * 31, "value": 1}, {"label": "b", "value": 2}]
    err(script([scene(1, "grafico", short=True, chart=ch)] + BASE_TAIL), "chart")
    tl = [{"when": "w" * 17, "label": "a"}, {"when": "b", "label": "c"}]
    err(script([scene(1, "linea", short=True, timeline=tl)] + BASE_TAIL), "timeline")
    tl = [{"when": "a", "label": "l" * 61}, {"when": "b", "label": "c"}]
    err(script([scene(1, "linea", short=True, timeline=tl)] + BASE_TAIL), "timeline")
    err(script([scene(1, short=True, source="s" * 81)] + BASE_TAIL), "source")
