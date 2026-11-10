import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    timezone: str = "America/Santiago"
    publish_hour: int = 7
    feeds: list[str] = field(default_factory=list)
    llm_provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-5.5"
    max_stories: int = 6
    pool_size: int = 30
    site_url: str = ""
    tts_provider: str = "openrouter"
    tts_model: str = ""
    tts_voice: str = ""


def load_config(path: Path = Path("config.toml")) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


LLM_PROVIDERS = ("openrouter", "anthropic")
TTS_PROVIDERS = ("openrouter", "openai", "elevenlabs")


def validate_config(config: Config) -> None:
    """Falla con un mensaje claro si ``config.toml`` conserva la URL de ejemplo
    o nombra un proveedor desconocido."""
    if config.llm_provider not in LLM_PROVIDERS:
        raise ValueError(f"llm_provider desconocido: {config.llm_provider!r} "
                         f"(use {' o '.join(repr(p) for p in LLM_PROVIDERS)})")
    if config.tts_provider not in TTS_PROVIDERS:
        raise ValueError(f"tts_provider desconocido: {config.tts_provider!r} "
                         f"(use {', '.join(repr(p) for p in TTS_PROVIDERS)})")
    url = config.site_url or ""
    if not url.startswith("https://") or "example." in url:
        raise ValueError(
            f"site_url inválida ({url!r}): edita config.toml y pon "
            "https://<tu-usuario>.github.io/<nombre-del-repo> (empieza por https://, "
            "sin 'example.')")
