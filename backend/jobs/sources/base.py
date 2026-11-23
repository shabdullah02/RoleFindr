from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NormalizedJob:
    external_id: str
    title: str
    location: str
    remote: bool
    url: str
    apply_url: str
    description: str
    posted_at: datetime | None
    company_name: str = ""
