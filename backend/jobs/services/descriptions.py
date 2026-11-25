from django.utils import timezone

from jobs.models import Job, Profile
from jobs.services import budget
from jobs.services.filters import check_job
from jobs.sources.linkedin_detail import fetch_description


def pending_jobs(profile: Profile):
    """Open LinkedIn jobs with no description that pass every filter except the description one."""
    for job in Job.objects.filter(source="linkedin", status="open", description="").order_by("-posted_at"):
        if check_job(job, profile, require_description=False).passed:
            yield job


def fill_descriptions(profile: Profile, fetch=fetch_description, limit: int | None = None) -> dict:
    allowed = budget.remaining("description")
    if limit is not None:
        allowed = min(allowed, limit)
    done = empty = 0
    for job in pending_jobs(profile):
        if done + empty >= allowed:
            break
        text = fetch(job.url)  # raises LinkedInBlocked on 429: caller stops the run
        budget.record("description")
        job.description_fetched_at = timezone.now()
        if text:
            job.description = text
            done += 1
        else:
            empty += 1  # fetched but empty: timestamp stops endless retries
        job.save(update_fields=["description", "description_fetched_at"])
    return {"filled": done, "empty": empty, "budget_left": budget.remaining("description")}
