from datetime import date, datetime, timezone

from radio.archive import (ArchivedStory, DayRecord, load_week, prune_days, save_day,
                           story_to_archived)
from radio.models import Story


def rec(day, title="T"):
    st = ArchivedStory(id=f"id-{day}", title="Titular", url="http://x", source="Fuente",
                       summary="Resumen", body="Cuerpo")
    return DayRecord(day=day, title=title, script="Guion del día.", stories=[st])


def test_save_and_load_roundtrip(tmp_path):
    a, b = rec(date(2026, 11, 9), "A"), rec(date(2026, 11, 10), "B")
    save_day(tmp_path, b)
    save_day(tmp_path, a)
    assert load_week(tmp_path, date(2026, 11, 10)) == [a, b]


def test_load_week_skips_missing_days_and_out_of_window(tmp_path):
    for d in (date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 8), date(2026, 11, 10)):
        save_day(tmp_path, rec(d))
    got = load_week(tmp_path, date(2026, 11, 10), days=7)
    assert [r.day for r in got] == [date(2026, 11, 5), date(2026, 11, 8), date(2026, 11, 10)]


def test_load_week_without_directory_is_empty(tmp_path):
    assert load_week(tmp_path / "nada", date(2026, 11, 10)) == []


def test_story_body_is_truncated_to_max_body():
    s = Story(id="i", title="t", url="u", source="s",
              published=datetime(2026, 11, 10, tzinfo=timezone.utc), summary="r", body="x" * 5000)
    assert len(story_to_archived(s).body) == 4000
    assert story_to_archived(s, max_body=10).body == "x" * 10


def test_story_without_body_stays_none():
    s = Story(id="i", title="t", url="u", source="s",
              published=datetime(2026, 11, 10, tzinfo=timezone.utc), summary="r")
    assert story_to_archived(s).body is None


def test_prune_days_keeps_newest(tmp_path):
    days = [date.fromordinal(date(2026, 9, 1).toordinal() + i) for i in range(62)]
    for d in days:
        save_day(tmp_path, rec(d))
    removed = prune_days(tmp_path, keep=60)
    assert removed == [f"{days[0].isoformat()}.json", f"{days[1].isoformat()}.json"]
    assert len(list((tmp_path / "days").glob("*.json"))) == 60
