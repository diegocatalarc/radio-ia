"""Registro diario persistente: guion y fuentes de cada episodio, para el resumen semanal."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from radio.models import Story

MAX_BODY = 4000


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@dataclass
class ArchivedStory:
    id: str
    title: str
    url: str
    source: str
    summary: str
    body: str | None


@dataclass
class DayRecord:
    day: date
    title: str
    script: str
    stories: list[ArchivedStory]


def story_to_archived(s: Story, max_body: int = MAX_BODY) -> ArchivedStory:
    body = s.body[:max_body] if s.body is not None else None
    return ArchivedStory(id=s.id, title=s.title, url=s.url, source=s.source,
                         summary=s.summary, body=body)


def _path(site_dir: Path, day: date) -> Path:
    return Path(site_dir) / "days" / f"{day.isoformat()}.json"


def save_day(site_dir: Path, record: DayRecord) -> Path:
    payload = asdict(record)
    payload["day"] = record.day.isoformat()
    path = _path(site_dir, record.day)
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return path


def _load(path: Path) -> DayRecord:
    d = json.loads(path.read_text(encoding="utf-8"))
    return DayRecord(day=date.fromisoformat(d["day"]), title=d["title"], script=d["script"],
                     stories=[ArchivedStory(**s) for s in d["stories"]])


def load_week(site_dir: Path, end_day: date, days: int = 7) -> list[DayRecord]:
    """Registros con ``end_day - days < day <= end_day``, ordenados; ignora los que faltan."""
    out = []
    for i in range(days - 1, -1, -1):
        p = _path(site_dir, end_day - timedelta(days=i))
        if p.exists():
            out.append(_load(p))
    return out


def prune_days(site_dir: Path, keep: int = 60) -> list[str]:
    """Borra los registros más antiguos dejando ``keep``; devuelve los nombres borrados."""
    files = sorted((Path(site_dir) / "days").glob("*.json"))
    removed = []
    for f in files[:max(0, len(files) - keep)]:
        f.unlink()
        removed.append(f.name)
    return removed
