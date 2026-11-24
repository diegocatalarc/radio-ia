from datetime import date

from radio.archive import ArchivedStory, DayRecord
from radio.video.material import week_material


def day(d, ids=("a",), script="Guion con 42 millones."):
    sts = [ArchivedStory(id=i, title=f"T{i}", url=f"http://x/{i}", source="Fuente",
                         summary="Resumen 7", body="Cuerpo 99") for i in ids]
    return DayRecord(day=d, title="Titulo", script=script, stories=sts)


def test_week_material_includes_story_bodies_and_daily_scripts():
    mat = week_material([day(date(2026, 11, 9)), day(date(2026, 11, 10), ids=("b",))])
    by_id = {s.id: s for s in mat}
    assert by_id["a"].body == "Cuerpo 99" and by_id["a"].summary == "Resumen 7"
    assert by_id["_script-2026-11-10"].body == "Guion con 42 millones."
    assert len(mat) == 4


def test_week_material_dedupes_repeated_story_ids():
    mat = week_material([day(date(2026, 11, 9)), day(date(2026, 11, 10))])
    assert [s.id for s in mat].count("a") == 1
