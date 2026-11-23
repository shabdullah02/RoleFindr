# backend/jobs/sources/lever.py  (replaces previous version)
import time
from datetime import datetime, timezone

import requests

from .base import NormalizedJob

HOSTS = ("https://api.lever.co", "https://api.eu.lever.co")
PAGE_SIZE = 100  # VERIFY max limit
DELAY = 1.0  # seconds between requests; VERIFY against Lever's robots.txt


def _get(host: str, slug: str, skip: int):
    """One page. Returns a list, or None on 404. Retries once if the body is not JSON."""
    for _ in range(2):
        resp = requests.get(
            f"{host}/v0/postings/{slug}",
            params={"mode": "json", "skip": skip, "limit": PAGE_SIZE},
            timeout=20,
        )
        time.sleep(DELAY)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        if "json" in resp.headers.get("Content-Type", ""):
            return resp.json()
    raise ValueError(f"Lever returned non-JSON for {slug}")


def _fetch_all(host: str, slug: str):
    postings, skip = [], 0
    while True:
        page = _get(host, slug, skip)
        if page is None:
            return None if skip == 0 else postings
        postings.extend(page)
        if len(page) < PAGE_SIZE:
            return postings
        skip += PAGE_SIZE


def _normalize(p: dict) -> NormalizedJob:
    loc = (p.get("categories") or {}).get("location") or ""
    created = p.get("createdAt")
    return NormalizedJob(
        external_id=p["id"],
        title=p["text"],
        location=loc,
        remote=p.get("workplaceType") == "remote" or "remote" in loc.lower(),
        url=p["hostedUrl"],
        apply_url=p.get("applyUrl") or p["hostedUrl"],
        description=p.get("descriptionPlain") or "",
        posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
    )


def fetch(slug: str) -> list[NormalizedJob]:
    for host in HOSTS:  # global first, EU if the site is not found
        postings = _fetch_all(host, slug)
        if postings is not None:
            return [_normalize(p) for p in postings]
    raise LookupError(f"Lever site not found on global or EU host: {slug}")