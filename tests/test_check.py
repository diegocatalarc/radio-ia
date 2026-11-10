import json
from datetime import datetime
from zoneinfo import ZoneInfo

from radio import check, correct
from radio.state import State

UTC = ZoneInfo("UTC")


def write_eps(site, days, extra_mp3=()):
    (site / "episodes").mkdir(parents=True, exist_ok=True)
    eps = []
    for d in days:
        name = f"episodes/episodio-{d}.mp3"
        (site / name).write_bytes(b"x")
        eps.append({"day": d, "mp3_path": name})
    (site / "episodes.json").write_text(json.dumps(eps), encoding="utf-8")
    for n in extra_mp3:
        (site / "episodes" / n).write_bytes(b"x")


def test_exists_today_true(tmp_path):
    write_eps(tmp_path, ["2026-11-10", "2026-11-09"])
    now = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert check.episode_exists_today(tmp_path, "America/Santiago", now)


def test_exists_today_false_when_only_yesterday(tmp_path):
    write_eps(tmp_path, ["2026-11-09"])
    now = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert not check.episode_exists_today(tmp_path, "America/Santiago", now)


def test_exists_today_missing_file_or_empty(tmp_path):
    now = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert not check.episode_exists_today(tmp_path, "America/Santiago", now)
    (tmp_path / "episodes.json").write_text("[]")
    assert not check.episode_exists_today(tmp_path, "America/Santiago", now)


def test_uses_configured_timezone_for_day(tmp_path):
    write_eps(tmp_path, ["2026-11-09"])
    # 02:00 UTC on Nov 10 is still Nov 9 in Santiago (UTC-3).
    now = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)
    assert check.episode_exists_today(tmp_path, "America/Santiago", now)
    assert not check.episode_exists_today(tmp_path, "UTC", now)


def test_naive_now_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        check.episode_exists_today(tmp_path, "UTC", datetime(2026, 1, 1))


def test_prune_removes_only_unreferenced_mp3(tmp_path):
    write_eps(tmp_path, ["2026-11-10"], extra_mp3=["episodio-2026-01-01.mp3"])
    (tmp_path / "episodes" / "notes.txt").write_text("keep")
    removed = check.prune_unreferenced_mp3(tmp_path)
    assert removed == ["episodio-2026-01-01.mp3"]
    assert (tmp_path / "episodes" / "episodio-2026-11-10.mp3").exists()
    assert (tmp_path / "episodes" / "notes.txt").exists()


def test_prune_noop_without_episodes_json(tmp_path):
    (tmp_path / "episodes").mkdir()
    (tmp_path / "episodes" / "a.mp3").write_bytes(b"x")
    assert check.prune_unreferenced_mp3(tmp_path) == []
    assert (tmp_path / "episodes" / "a.mp3").exists()


def test_main_exit_codes(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('timezone = "UTC"\n')
    monkeypatch.chdir(tmp_path)
    assert check.main([]) == 1
    today = datetime.now(UTC).date().isoformat()
    write_eps(tmp_path / "site", [today])
    assert check.main([]) == 0


def test_main_prune_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_eps(tmp_path / "site", ["2026-11-10"], extra_mp3=["old.mp3"])
    assert check.main(["--prune"]) == 0
    assert not (tmp_path / "site" / "episodes" / "old.mp3").exists()


def test_correct_cli_adds_correction(tmp_path):
    p = tmp_path / "state.json"
    assert correct.main(["Corrección: la cifra era 5%", "--state", str(p)]) == 0
    assert correct.main(["otra", "--state", str(p)]) == 0
    assert State.load(p).corrections == ["Corrección: la cifra era 5%", "otra"]


def test_correct_cli_rejects_empty(tmp_path):
    assert correct.main(["   ", "--state", str(tmp_path / "s.json")]) == 1
    assert not (tmp_path / "s.json").exists()
