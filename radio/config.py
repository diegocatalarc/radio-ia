import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    timezone: str = "America/Santiago"
    publish_hour: int = 7
    feeds: list[str] = field(default_factory=list)
    model: str = "claude-sonnet-5-5"
    max_stories: int = 6
    pool_size: int = 30
    site_url: str = ""
    tts_provider: str = "openai"
    tts_voice: str = ""


def load_config(path: Path = Path("config.toml")) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def validate_config(config: Config) -> None:
    """Falla con un mensaje claro si ``config.toml`` conserva la URL de ejemplo."""
    url = config.site_url or ""
    if not url.startswith("https://") or "example." in url:
        raise ValueError(
            f"site_url inválida ({url!r}): edita config.toml y pon "
            "https://<tu-usuario>.github.io/<nombre-del-repo> (empieza por https://, "
            "sin 'example.')")
