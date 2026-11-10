from dataclasses import dataclass
from datetime import datetime


@dataclass
class Story:
    id: str
    title: str
    url: str
    source: str
    published: datetime
    summary: str
    body: str | None = None
