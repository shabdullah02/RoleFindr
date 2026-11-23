from django.conf import settings
from django.db import models


class MasterResume(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="master_resumes")
    json_resume = models.JSONField()  # JSON Resume schema
    source_file = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "version"], name="uniq_master_resume_version")]
