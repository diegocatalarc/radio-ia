from pathlib import Path

import pytest

from radio.config import Config, load_config, validate_config


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
    assert cfg.tts_provider == "openrouter"
    assert cfg.llm_provider == "openrouter"
    assert cfg.tts_voice == ""


def test_defaults_pool_and_max_stories():
    c = Config()
    assert c.pool_size == 30 and c.max_stories == 6


@pytest.mark.parametrize("url", ["", "http://u.github.io/r", "https://example.github.io/radio-ia",
                                 "https://example.org/x", "u.github.io/r"])
def test_placeholder_or_invalid_site_url_rejected(url):
    with pytest.raises(ValueError, match="config.toml"):
        validate_config(Config(site_url=url))


def test_valid_site_url_accepted():
    validate_config(Config(site_url="https://diego.github.io/radio-ia"))


def test_unknown_providers_rejected():
    ok = "https://diego.github.io/radio-ia"
    with pytest.raises(ValueError, match="llm_provider.*foo"):
        validate_config(Config(site_url=ok, llm_provider="foo"))
    with pytest.raises(ValueError, match="tts_provider.*bar"):
        validate_config(Config(site_url=ok, tts_provider="bar"))
    for llm in ("openrouter", "anthropic"):
        for tts in ("openrouter", "openai", "elevenlabs"):
            validate_config(Config(site_url=ok, llm_provider=llm, tts_provider=tts))
