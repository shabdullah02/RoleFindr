from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from jobs.models import Job, Profile
from jobs.services.filters import check_job


class Command(BaseCommand):
    help = "Run hard filters for a user's Profile over open LinkedIn jobs"

    def add_arguments(self, p):
        p.add_argument("--email")

    def handle(self, *args, email=None, **opts):
        User = get_user_model()
        user = User.objects.filter(email=email).first() if email else User.objects.first()
        if not user:
            raise CommandError("no user found; run createsuperuser first")
        profile, _ = Profile.objects.get_or_create(user=user)
        passed = total = 0
        for job in Job.objects.filter(source="linkedin", status="open").order_by("-posted_at"):
            r = check_job(job, profile)
            total += 1
            passed += r.passed
            self.stdout.write(f"{'PASS' if r.passed else 'FAIL'} {job.title[:50]:50} {','.join(r.reasons)}")
        self.stdout.write(f"{passed}/{total} passed for {user.email}")
