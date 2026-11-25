from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class MasterResume(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="master_resumes")
    json_resume = models.JSONField()  # JSON Resume schema
    source_file = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["user", "version"],
                name="uniq_master_resume_version",
            )
        ]


class ResumeUpload(models.Model):
    """Draft parse result. MasterResume is created only after the user reviews and confirms."""

    class Status(models.TextChoices):
        PENDING = "pending"
        PARSING = "parsing"
        PARSED = "parsed"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resume_uploads")
    file = models.FileField(upload_to="resumes/")  # private storage; S3 later, never served publicly
    original_filename = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=300, blank=True)
    parsed_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
