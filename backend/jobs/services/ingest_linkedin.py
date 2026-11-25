from django.utils import timezone

from jobs.models import Job
from jobs.sources.linkedin import LinkedInGuestSource


def ingest_linkedin(term, location="Pakistan", n=50, source=None, scrape=None) -> dict:
    source = source or LinkedInGuestSource()
    now = timezone.now()
    created = updated = 0
    for nj in source.fetch(term, location, n, scrape=scrape):
        defaults = {
            "company": None,
            "company_name": nj.company_name,
            "title": nj.title,
            "location": nj.location,
            "remote": nj.remote,
            "url": nj.url,
            "apply_url": nj.apply_url,
            "posted_at": nj.posted_at,
            "status": Job.Status.OPEN,
            "fetched_at": now,
        }
        if nj.description:  # never overwrite a fetched description with an empty one
            defaults["description"] = nj.description
        _, c = Job.objects.update_or_create(source="linkedin", external_id=nj.external_id, defaults=defaults)
        created += c
        updated += not c
    return {"created": created, "updated": updated}
