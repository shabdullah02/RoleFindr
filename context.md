# Project: RoleFindr (Job Application Automation Platform)

## Goal
Build a platform where a user signs up, uploads a resume, and the system
finds matching jobs, scores them against the job description and skills,
tailors the resume per job, helps the user apply, and tracks every
application and follow-up. Reuse open-source components wherever possible
instead of reinventing them.

## Decisions made
- Human in the loop: the platform redirects the user to the real apply page
  and the user clicks Submit. No fully automated submission.
- No stored LinkedIn credentials or session cookies on our servers.
- Discovery uses LinkedIn guest search plus public ATS endpoints
  (Greenhouse, Lever, Ashby, Workable) and JobSpy for other boards.
- LinkedIn Easy Apply and external forms are filled by a Chrome extension
  (Manifest V3) running in the user's own browser. It requests no cookies
  permission.
- Plain Django app, not a CMS. Wagtail only later, if a marketing
  site or blog is needed.
- Daily per-user apply cap, with a random value in a 15-23 range.

## Workflow
1. Onboarding: resume upload, preferences, pre-answers to common questions
2. Parse resume to JSON Resume schema (Gemini structured output); user reviews
3. Scheduled discovery -> normalize -> dedupe (unique source + external_id)
4. Hard filters, embedding first pass, Gemini second pass (career-ops rubric)
5. Inbox -> user approves/rejects
6. Tailor resume (only facts from the master resume) + reviewer pass for
   fabricated claims -> render PDF
7. Apply page: tailored resume, cover letter, suggested answers, open apply URL
8. Extension autofills; user clicks Submit
9. Confirmation (extension detects success page, or user clicks "I applied")
10. Tracker: applied date, resume version, JD snapshot, follow-up reminders

## Application statuses
inbox -> approved -> ready -> applied -> interview / offer / rejected

## Stack
Django + DRF, PostgreSQL + pgvector, Celery + Redis, django-allauth (JWT for
the extension), HTMX or React frontend, S3-compatible storage, Gemini API,
Docker Compose, Sentry.

## Open-source components
- Ingestion: JobSpy (MIT), public ATS APIs
- Parsing: JSON Resume schema, pdfplumber, python-docx
- Scoring: career-ops rubric (MIT), sentence-transformers, pgvector
- Tailoring: Resume-Matcher prompts (verify license), reviewer-agent idea
  from ai-job-search (license unverified; idea only)
- PDF: RenderCV or WeasyPrint
- Testing: Playwright (selector tests against saved page snapshots)
- Read-only inspiration, do NOT copy code (AGPL-3.0): ApplyPilot, JustHireMe
- Not for seeding data: feashliaa/job-board-aggregator (commercial use of
  its datasets requires the author's permission)

## Build order
1. Job model + Greenhouse/Lever ingestion + Gemini scoring printed to console
2. Resume upload and parsing
3. Dashboard: inbox, approve, reject
4. Tailoring + reviewer pass + PDF
5. Apply page + tracker + reminders
6. JobSpy + LinkedIn guest search; measure Easy Apply vs external link share
7. Extension autofill: Greenhouse/Lever first, LinkedIn Easy Apply last

## Open questions
- Real share of Easy Apply vs external listings (measure with ~100 guest listings)
- Current license of Resume-Matcher and ai-job-search
- Frontend choice: HTMX vs React
- Target markets and job boards (Pakistani boards such as Rozee.pk are not
  covered by JobSpy)

## Constraints
- LinkedIn's terms prohibit scraping and automation even when logged out;
  expect IP blocks, so plan for proxies at volume and tell users about the risk
- Resume tailoring must never invent skills, employers, or degrees
- Check every license before copying code into a hosted product

## Instructions for Claude
- Be direct about ToS, security, and legal risks; don't soften them.
- Prefer working code and small vertical slices over more architecture
  discussion.
- When suggesting a library or tool, state its license and whether it is safe
  for a hosted commercial product.
- Keep Django models, API shapes, and status names consistent with this doc.
- Flag anything that would require storing user credentials or session
  cookies server-side.
