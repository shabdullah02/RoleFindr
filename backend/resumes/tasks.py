from celery import shared_task

from resumes.parsers import ResumeParseError
from resumes.services import run_parse


# Free-tier hosts cold-start: 90s client timeout, then backoff 15s, 30s, 60s.
@shared_task(autoretry_for=(ResumeParseError,), retry_backoff=15, retry_backoff_max=120, max_retries=3)
def parse_resume_task(upload_id):
    run_parse(upload_id)
