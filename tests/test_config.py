from pathlib import Path

from radio.config import load_config


def test_load_config_reads_timezone_and_feeds(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        'timezone = "America/Santiago"\n'
        "max_stories = 6\n"
        'feeds = ["https://a.example/feed", "https://b.example/feed"]\n'
    )
    cfg = load_config(p)
    assert cfg.timezone == "America/Santiago"
    assert cfg.feeds == ["https://a.example/feed", "https://b.example/feed"]
    assert cfg.max_stories == 6
    assert cfg.tts_provider == "openai"
    assert cfg.tts_voice == ""
