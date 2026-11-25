from django.db import transaction

from resumes.models import MasterResume, ResumeUpload
from resumes.parsers import ResumeIQParser, ResumeParseError, normalize


def run_parse(upload_id, parser=None) -> ResumeUpload:
    """Parse one upload. Retryable errors are re-raised so the Celery task can retry."""
    upload = ResumeUpload.objects.get(pk=upload_id)
    upload.status, upload.error = ResumeUpload.Status.PARSING, ""
    upload.save(update_fields=["status", "error"])
    try:
        with upload.file.open("rb") as f:
            content = f.read()
        parsed = (parser or ResumeIQParser()).parse(upload.original_filename, content)
    except ResumeParseError as e:
        upload.status, upload.error = ResumeUpload.Status.FAILED, str(e)[:300]
        upload.save(update_fields=["status", "error"])
        if e.retryable:
            raise
        return upload
    upload.status, upload.parsed_json = ResumeUpload.Status.PARSED, parsed.json_resume
    upload.save(update_fields=["status", "parsed_json"])
    return upload


def save_master(user, json_resume: dict, source_file: str = "") -> MasterResume:
    """New version each time. The user-reviewed master is the ground truth for the claims check."""
    with transaction.atomic():
        latest = MasterResume.objects.select_for_update().filter(user=user).order_by("-version").first()
        return MasterResume.objects.create(
            user=user, json_resume=normalize(json_resume), source_file=source_file,
            version=latest.version + 1 if latest else 1)
