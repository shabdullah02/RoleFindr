# backend/jobs/management/commands/score_jobs.py
"""
Management command: score_jobs
Usage:
  python manage.py score_jobs --resume fixtures/resume_reviewed.json --user test@example.com [--top 20]
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Score open jobs against a JSON Resume file and print a ranked table."

    def add_arguments(self, parser):
        parser.add_argument("--resume", required=True, help="Path to reviewed JSON Resume .json file")
        parser.add_argument("--user", required=True, help="User email")
        parser.add_argument("--top", type=int, default=None, help="Top N jobs to shortlist (default: settings.SCORING_TOP_N)")
        parser.add_argument("--threshold", type=int, default=None, help="Score threshold for inbox (default: settings.SCORING_THRESHOLD)")

    def handle(self, **options):
        from jobs.services.scoring import score_jobs_for_user
        from resumes.services import save_master

        # Load resume
        resume_path = options["resume"]
        try:
            with open(resume_path) as f:
                json_resume = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f"Cannot read resume file: {e}") from e

        # Get or create user
        email = options["user"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"User {email} not found. Create the user first.") from None

        # Determine resume version: use latest MasterResume or create one
        from resumes.models import MasterResume
        master = MasterResume.objects.filter(user=user).order_by("-version").first()
        if master:
            resume_version = master.version
            # Update the master if the resume content changed
            if master.json_resume != json_resume:
                master = save_master(user, json_resume, source_file=resume_path)
                resume_version = master.version
                self.stdout.write(f"Created MasterResume v{resume_version}")
        else:
            master = save_master(user, json_resume, source_file=resume_path)
            resume_version = master.version
            self.stdout.write(f"Created MasterResume v{resume_version}")

        self.stdout.write(f"Scoring for {email} (resume v{resume_version})...")
        self.stdout.write("")

        kwargs = {}
        if options["top"]:
            kwargs["top_n"] = options["top"]
        if options["threshold"] is not None:
            kwargs["threshold"] = options["threshold"]

        results = score_jobs_for_user(user, json_resume, resume_version, **kwargs)

        if not results:
            self.stdout.write("No jobs matched after filtering and scoring.")
            return

        # Print table
        self.stdout.write(f"{'Score':>5}  {'Embed':>6}  {'Title':<40}  {'Company':<25}  {'Matched Skills':<40}  {'Gaps'}")
        self.stdout.write("-" * 160)
        for r in results:
            from jobs.models import Job
            try:
                job = Job.objects.get(id=r["job_id"])
            except Job.DoesNotExist:
                continue
            skills_str = ", ".join(r.get("matched_skills", [])[:5])
            gaps_str = ", ".join(r.get("gaps", [])[:3])
            embed = f"{r.get('embed_score', 0):.3f}" if r.get("embed_score") else "N/A"
            self.stdout.write(
                f"{r.get('llm_score', 0):>5}  {embed:>6}  "
                f"{job.title[:40]:<40}  {(job.company_name or '')[:25]:<25}  "
                f"{skills_str[:40]:<40}  {gaps_str}"
            )

        self.stdout.write("")
        self.stdout.write(f"Total: {len(results)} jobs scored")
        above = sum(1 for r in results if (r.get("llm_score") or 0) >= (options.get("threshold") or 70))
        self.stdout.write(f"Above threshold: {above} (created as Application inbox)")
