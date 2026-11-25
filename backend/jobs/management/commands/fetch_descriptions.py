from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from jobs.models import Profile
from jobs.services.descriptions import fill_descriptions
from jobs.sources.linkedin import LinkedInBlocked


class Command(BaseCommand):
    help = "Fetch descriptions only for jobs that pass title/location filters, within the daily budget"

    def add_arguments(self, p):
        p.add_argument("--email")
        p.add_argument("--limit", type=int)

    def handle(self, *args, email=None, limit=None, **opts):
        User = get_user_model()
        user = User.objects.filter(email=email).first() if email else User.objects.first()
        if not user:
            raise CommandError("no user found")
        profile, _ = Profile.objects.get_or_create(user=user)
        try:
            self.stdout.write(str(fill_descriptions(profile, limit=limit)))
        except LinkedInBlocked as e:
            raise CommandError(str(e))
