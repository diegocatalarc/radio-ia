"""Persistent state: stories already used on previous days and pending corrections."""
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from radio.models import Story

KEEP_DAYS = 14


@dataclass
class State:
    used: dict[str, str] = field(default_factory=dict)  # story id -> ISO day
    corrections: list[str] = field(default_factory=list)
    current_day: date | None = None  # defaults to date.today()

    @classmethod
    def load(cls, path) -> "State":
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(used=dict(data.get("used", {})),
                   corrections=list(data.get("corrections", [])))

    def save(self, path) -> None:
        p = Path(path)
        latest = max((date.fromisoformat(d) for d in self.used.values()), default=None)
        if latest is not None:
            cutoff = latest - timedelta(days=KEEP_DAYS - 1)
            self.used = {i: d for i, d in self.used.items()
                         if date.fromisoformat(d) >= cutoff}
        payload = json.dumps({"used": self.used, "corrections": self.corrections},
                             ensure_ascii=False, indent=2)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def filter_new(self, stories: list[Story]) -> list[Story]:
        today = (self.current_day or date.today()).isoformat()
        # Stories marked today stay available so a same-day rerun is identical.
        return [s for s in stories if self.used.get(s.id, today) >= today]

    def mark_used(self, stories: list[Story], day: date) -> None:
        for s in stories:
            self.used[s.id] = day.isoformat()

    def add_correction(self, text: str) -> None:
        self.corrections.append(text)

    def pop_corrections(self) -> list[str]:
        out, self.corrections = self.corrections, []
        return out
