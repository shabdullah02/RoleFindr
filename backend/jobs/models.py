# backend/jobs/models.py
from django.conf import settings
from django.db import models


class Company(models.Model):
    class Ats(models.TextChoices):
        GREENHOUSE = "greenhouse"
        LEVER = "lever"
        ASHBY = "ashby"
        WORKABLE = "workable"

    name = models.CharField(max_length=200)
    ats_type = models.CharField(max_length=16, choices=Ats.choices)
    slug = models.CharField(max_length=200)  # Lever slugs are case-sensitive; keep as given
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ats_type", "slug"], name="uniq_company_ats_slug")]

    def __str__(self):
        return f"{self.name} ({self.ats_type}:{self.slug})"


class Job(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    class ApplyMethod(models.TextChoices):
        EASY_APPLY = "easy_apply"
        EXTERNAL_FORM = "external_form"
        EMAIL = "email"
        UNKNOWN = "unknown"

    source = models.CharField(max_length=32)
    external_id = models.CharField(max_length=255)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL)
    company_name = models.CharField(max_length=300, blank=True)
    title = models.CharField(max_length=500)
    location = models.CharField(max_length=500, blank=True)
    remote = models.BooleanField(default=False)
    url = models.URLField(max_length=1000)
    apply_url = models.URLField(max_length=1000)
    apply_method = models.CharField(max_length=16, choices=ApplyMethod.choices, default=ApplyMethod.UNKNOWN)
    description = models.TextField(blank=True)  # plain text; never render third-party HTML
    posted_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    # embedding (vector) is added in slice 3 with the pgvector Python package

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "external_id"], name="uniq_job_source_external")]
        indexes = [models.Index(fields=["company", "status"])]

class Profile(models.Model):
    class RemotePref(models.TextChoices):
        ANY = "any"
        REMOTE_ONLY = "remote_only"
        ONSITE_ONLY = "onsite_only"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    titles = models.JSONField(default=list, blank=True)
    locations = models.JSONField(default=list, blank=True)
    remote_pref = models.CharField(max_length=12, choices=RemotePref.choices, default=RemotePref.ANY)
    salary_floor = models.PositiveIntegerField(null=True, blank=True)
    blocklist = models.JSONField(default=list, blank=True)
    work_auth = models.CharField(max_length=100, blank=True)
    notice_period = models.CharField(max_length=50, blank=True)
    links = models.JSONField(default=dict, blank=True)


class JobMatch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    embed_score = models.FloatField(null=True, blank=True)
    llm_score = models.PositiveSmallIntegerField(null=True, blank=True)
    matched_skills = models.JSONField(default=list, blank=True)
    gaps = models.JSONField(default=list, blank=True)
    rationale = models.TextField(blank=True)
    resume_version = models.PositiveIntegerField()
    scored_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "job", "resume_version"],
                                               name="uniq_jobmatch_user_job_resume")]
