import os
import re
from datetime import UTC, datetime, time

from django.conf import settings
import pandas as pd

from .base import NormalizedJob


def _s(v) -> str:
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


class LinkedInBlocked(Exception):
    pass


class LinkedInGuestSource:
    name = "linkedin"

    def fetch(self, term, location="Pakistan", n=50, scrape=None,
              fetch_description=False) -> list[NormalizedJob]:
        if scrape is None:
            from jobspy import scrape_jobs as scrape
        df = scrape(site_name=["linkedin"], search_term=term, location=location,
                    results_wanted=n, linkedin_fetch_description=fetch_description,
                    proxies=settings.LINKEDIN_PROXIES or None, verbose=1)
        if df is None:  # empty frame is valid; None is an error
            raise LinkedInBlocked("scrape returned None")
        return [j for j in map(self._normalize, df.to_dict("records")) if j is not None]

    @staticmethod
    def _normalize(r) -> NormalizedJob | None:
        url = _s(r.get("job_url"))
        m = re.search(r"(\d{6,})(?:[/?]|$)", url)
        if not m:
            return None
        direct = _s(r.get("job_url_direct"))
        d = r.get("date_posted")
        posted = (datetime.combine(d, time.min, tzinfo=UTC)
                  if d is not None and not pd.isna(d) and hasattr(d, "year") else None)
        loc = _s(r.get("location"))
        return NormalizedJob(
            external_id=m.group(1), title=_s(r.get("title")), location=loc,
            remote=bool(r.get("is_remote")) or "remote" in loc.lower()
            or "remote" in _s(r.get("title")).lower(),
            url=url, apply_url=direct or url,
            description=_s(r.get("description")), posted_at=posted,
            company_name=_s(r.get("company")) or _s(r.get("company_name")))
