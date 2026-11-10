from datetime import date, datetime, timedelta

from radio.models import Story
from radio.state import State


def story(i: str) -> Story:
    return Story(id=i, title=i, url=f"http://x/{i}", source="s",
                 published=datetime(2026, 1, 1), summary="")


def test_filter_new_drops_stories_used_on_previous_days():
    st = State()
    st.mark_used([story("a")], date(2026, 1, 1))
    st.mark_used([story("b")], date(2026, 1, 2))
    st.current_day = date(2026, 1, 3)
    assert [s.id for s in st.filter_new([story("a"), story("b"), story("c")])] == ["c"]


def test_rerun_same_day_keeps_stories_of_that_day():
    st = State()
    st.mark_used([story("a")], date(2026, 1, 1))
    st.mark_used([story("b")], date(2026, 1, 2))
    st.current_day = date(2026, 1, 2)
    assert [s.id for s in st.filter_new([story("a"), story("b")])] == ["b"]


def test_filter_new_defaults_to_real_today():
    st = State()
    st.mark_used([story("a")], date.today())
    st.mark_used([story("b")], date.today() - timedelta(days=1))
    assert [s.id for s in st.filter_new([story("a"), story("b")])] == ["a"]


def test_corrections_are_returned_once():
    st = State()
    st.add_correction("fix")
    assert st.pop_corrections() == ["fix"]
    assert st.pop_corrections() == []


def test_load_missing_file_is_empty(tmp_path):
    st = State.load(tmp_path / "nope.json")
    assert st.filter_new([story("a")])[0].id == "a"
    assert st.pop_corrections() == []


def test_save_load_roundtrip_and_prunes_to_14_days(tmp_path):
    p = tmp_path / "state.json"
    st = State()
    for n in range(20):
        st.mark_used([story(f"s{n}")], date(2026, 1, 1) + timedelta(days=n))
    st.add_correction("c")
    st.save(p)
    assert not list(tmp_path.glob("*.tmp"))
    loaded = State.load(p)
    assert len(loaded.used) == 14
    loaded.current_day = date(2026, 2, 1)
    assert [s.id for s in loaded.filter_new([story("s0"), story("s19")])] == ["s0"]
    assert loaded.pop_corrections() == ["c"]
