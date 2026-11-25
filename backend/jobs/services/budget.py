from django.conf import settings
from django.utils import timezone

from jobs.models import ScrapeLog

LIMITS = {"search": "LINKEDIN_MAX_SEARCHES_PER_DAY", "description": "LINKEDIN_MAX_DESCRIPTIONS_PER_DAY"}
DEFAULTS = {"search": 3, "description": 40}


def remaining(kind: str) -> int:
    limit = getattr(settings, LIMITS[kind], DEFAULTS[kind])
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = ScrapeLog.objects.filter(kind=kind, at__gte=start).count()
    return max(limit - used, 0)


def record(kind: str) -> None:
    ScrapeLog.objects.create(kind=kind)
