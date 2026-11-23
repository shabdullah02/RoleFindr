# backend/jobs/management/commands/ingest_linkedin.py
from django.core.management.base import BaseCommand, CommandError

from jobs.services.ingest_linkedin import ingest_linkedin
from jobs.sources.linkedin import LinkedInBlocked


class Command(BaseCommand):
    help = "Fetch LinkedIn guest-search jobs for a term and location"

    def add_arguments(self, p):
        p.add_argument("term")
        p.add_argument("--location", default="Pakistan")
        p.add_argument("--n", type=int, default=50)

    def handle(self, *args, term, location, n, **opts):
        try:
            self.stdout.write(str(ingest_linkedin(term, location, n)))
        except LinkedInBlocked as e:
            raise CommandError(str(e))