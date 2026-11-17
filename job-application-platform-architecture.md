# RoleFindr: Architecture & Context

Status: decided, except items marked [CONFIRM] or [VERIFY].
Source of truth for the repo. Move each decision into docs/adr/ when the repo is created.
Extension auth and token model (section 7) decided 2026-11-17; supersedes the
single ExtensionToken design from earlier drafts.

## 1. Product
Users sign up, upload a resume, and set preferences. The platform discovers jobs,
filters and scores them against the user's resume, tailors the resume per job,
prepares the application, and sends the user to the real apply page. The user
reviews and clicks Submit themselves. The platform then tracks the application
and follow-ups.

Target user: Pakistani computer science graduates applying to jobs.
Model: small free beta first, with a paid SaaS tier planned later.
Markets: global ATS job boards in v1. Pakistan-specific boards (e.g. Rozee.pk)
are out of v1 scope and would need custom adapters later.

Non-goals for v1:
- Fully automated submission
- Storing LinkedIn credentials or session cookies
- Closed ATS automation (Workday, Taleo, iCIMS, SuccessFactors)
- CMS or marketing site (Wagtail only later, if needed)

Note: the Chrome extension is optional. Without it the user copies suggested
answers manually, submits on the real site themselves, and clicks "I applied"
in the dashboard. The full discover -> score -> tailor -> track pipeline works
in the web app alone.

## 2. Principles (decided)
1. Human submits. Automation covers everything up to the final Submit click.
2. No LinkedIn credentials or session cookies on our servers, ever.
3. Browser extension runs in the user's own browser; no "cookies" permission.
4. Official or public endpoints first (ATS APIs), scraping second, LinkedIn supplementary.
5. Resume tailoring uses only facts present in the user's master resume.
6. Each stage works without the stages after it. Build vertical slices.
7. Check every license before copying code into the hosted product.
8. Standard stack: Next.js + React frontend, Django REST API backend.
9. The extension is optional; the platform is fully usable without it
   (manual "I applied" fallback).

## 3. System overview

Components:
1. Web app: Next.js + React + TypeScript (user dashboard)
2. API: Django REST Framework (also serves the extension)
3. Workers: Celery + Redis + Celery Beat (ingestion, scoring, tailoring, reminders)
4. Database: PostgreSQL + pgvector
5. Object storage: S3-compatible (MinIO locally) for resumes and PDFs
6. LLM layer: Gemini API
7. Resume service: ResumeIQ (existing project), wrapped behind an interface
8. Chrome extension: Manifest V3 autofill helper
9. Admin and ops: Django admin, Sentry, logs

Data flow:
  Sources -> Ingest worker -> Job (dedupe on source + external_id)
    -> Hard filters -> Embedding shortlist -> Gemini score -> Application(status=inbox)
  User approves -> Tailor worker -> TailoredResume (claims check, PDF)
    -> Application(status=ready) -> Apply page -> "Open application" opens apply_url
    -> Extension autofills -> user clicks Submit -> status=applied
    -> Tracker and reminders

## 4. Stack

| Layer | Choice | Status |
|---|---|---|
| Frontend | Next.js + React + TypeScript | Decided |
| Backend | Django + Django REST Framework | Decided |
| Auth | django-allauth; MFA module enabled later | Decided; 2FA planned |
| Database | PostgreSQL + pgvector | Decided |
| Queue | Celery + Redis + Celery Beat | Decided |
| LLM | Gemini API (parsing, scoring, tailoring, claims check) | Decided; see section 11 |
| Embeddings | Gemini embeddings | Decided |
| Resume service | ResumeIQ, wrapped behind an interface | Decided |
| PDF rendering | RenderCV (MIT) or WeasyPrint (BSD) | [CONFIRM] after 1-day test |
| File storage | S3-compatible | Decided |
| Extension | Chrome MV3, TypeScript | Decided |
| Testing | pytest, Vitest or Jest, Playwright | Decided |
| CI | GitHub Actions | Decided |
| Hosting | Free tier at beta, managed Postgres and Redis | [CONFIRM] exact provider |
| Monitoring | Sentry | Decided |

## 5. Data model (Django)

User(id, email, created_at, plan[free|pro], mfa_enabled)

Profile(user, titles[], locations[], remote_pref, salary_floor, blocklist[],
        work_auth, notice_period, links{})

MasterResume(user, json_resume, source_file, version, updated_at)
  json_resume follows the JSON Resume schema.

AnswerBank(user, question_key, answer, last_used)
  Pre-answered screening questions (work authorization, notice period, expected salary).

Company(id, name, ats_type[greenhouse|lever|ashby|workable], slug, active)

Job(id, source, external_id, company, title, location, remote, url, apply_url,
    apply_method, description, posted_at, fetched_at, embedding (vector),
    status[open|closed])
  UNIQUE(source, external_id)
  apply_method: easy_apply | external_form | email | unknown

JobMatch(user, job, embed_score, llm_score, matched_skills[], gaps[], rationale,
         resume_version, scored_at)
  UNIQUE(user, job, resume_version)

Application(id, user, job, status, resume_version, cover_letter, created_at,
            approved_at, ready_at, applied_at, notes)

TailoredResume(application, json_resume, pdf_path,
               claims_check{passed, flags[]}, model, created_at)

ApplicationEvent(application, type, payload, at)   # audit trail

FollowUp(application, due_at, type, done)

ExtensionDevice(user, name, family_id, refresh_token_hash,
                created_at, last_used_at, revoked_at)
ApplySession(device, application, token_hash, expires_at, revoked_at)

DailyApplyLog(user, date, cap, count)
  cap drawn at random from the integer array [15..23], once per user per day.

Application status flow:
  inbox -> approved -> ready -> applied -> interview -> offer
                              -> rejected | withdrawn | failed
  Only "applied" is set by a human action (user clicks Submit and confirms).
  The extension may set ready -> submitted_pending_confirm or ready -> failed;
  the user confirms applied in the popup or dashboard.

## 6. Pipelines

### 6.1 Onboarding
1. Sign up by email (Google login optional).
2. Upload resume (PDF or DOCX). Parse to JSON Resume via the ResumeIQ service.
3. User reviews and corrects the parsed data. Saved as MasterResume v1.
4. Set preferences (titles, locations, remote, salary floor, blocklist).
5. Pre-answer common questions into AnswerBank.

### 6.2 Discovery (scheduled via Celery Beat)
1. ATS sources: for each active Company slug, call the Greenhouse, Lever, Ashby,
   or Workable public job-board endpoint. One GET per company.
2. JobSpy (MIT): Indeed, Google, Naukri, Bayt. LinkedIn guest search is
   supplementary; see section 10.
3. User-pasted URLs: fetch and parse a single job page.
4. Normalize into Job. Upsert on (source, external_id). Mark jobs no longer
   returned as closed.
5. Detect apply_method from the apply URL and page signals.
6. Rate limiting, retries with backoff, per-source error counters. A failing
   source must never block other sources.

### 6.3 Scoring (two stages, controls LLM cost)
1. Hard filters: location, remote, title keywords, salary if present, blocklist.
2. Embedding shortlist: cosine similarity between resume and JD in pgvector;
   keep the top N.
3. Gemini pass on the shortlist only: score 0-100, matched skills, gaps, and
   rationale, using the rubric from ResumeIQ and career-ops as the starting prompt.
4. Cache by (resume_version, job_id). Rescore only when the resume or JD changes.
5. Jobs at or above the user's threshold (platform default 70) enter the inbox
   as Application(status=inbox).

### 6.4 Review
User approves or rejects in the inbox. Approve moves the application to
"approved" and triggers tailoring.

### 6.5 Tailoring
1. Input: MasterResume JSON plus the JD.
2. Gemini rewrites the summary, reorders skills, and emphasizes relevant
   experience. Output is JSON Resume. No new employers, dates, degrees, or skills.
3. Claims check: a second Gemini pass plus a deterministic diff. Every skill,
   employer, title, date, degree, and metric must exist in the master.
   Flags are shown to the user. A failed check blocks "ready".
4. Render PDF. Save TailoredResume. Status becomes "ready".
5. Optional cover letter under the same claims rule.

### 6.6 Apply (human submits)
1. Apply page shows: job summary, tailored PDF, cover letter, suggested answers
   from AnswerBank, claims-check flags, and the remaining daily count.
2. "Open application" messages the extension (externally_connectable,
   platform origin only). Without the extension installed, it opens apply_url
   in a plain new tab; see section 7.4 for the fallback.
3. The service worker opens apply_url, stores a tabId -> applicationId mapping
   in chrome.storage.session (no ID in the URL; page scripts can read
   location.hash), obtains a per-application session token, fills known
   fields, attaches the PDF, and stops at the final screen.
4. Unknown or custom questions are highlighted for the user and never guessed.
5. User reviews and clicks Submit on the real site.
6. The extension detects the success page and reports it. Fallback: the user
   clicks "I applied."
7. Status becomes "applied". DailyApplyLog increments. The cap is enforced.

### 6.7 Email-apply jobs
A prefilled mailto: link opens in the user's mail app. The user sends it, then
confirms "I applied." Status becomes "applied".

### 6.8 Tracker and reminders
Applied date, resume version, JD snapshot, status history, notes.
Reminders at 7 and 14 days, delivered as an email digest.

## 7. Extension auth and token model

Decided 2026-11-17. The user never pastes a token, tokens are short-lived, and
each apply action gets a token scoped to exactly one application. The URL
fragment carries no authority.

### 7.1 Token issuance
- OAuth 2.0 Authorization Code + PKCE through `chrome.identity.launchWebAuthFlow`;
  django-oauth-toolkit on the server (BSD-2-Clause; verify before adopting).
- Public client, PKCE-only, no client secret in the extension. Redirect URI
  from `chrome.identity.getRedirectURL()`.
- The user never re-enters credentials: an existing dashboard session skips
  login, and the flow shows only "Connect this browser? [Approve]".
- A logged-in dashboard may later hand the extension a short-lived bootstrap
  token via messaging to skip the approve screen. Deferred — keep the explicit
  consent step for Chrome Web Store review.

### 7.2 Token storage
| Token | Lifetime | Storage |
|---|---|---|
| Access token | 15 minutes | `chrome.storage.session` (memory-only, cleared on browser close) |
| Refresh token | 30 days, rotating | `chrome.storage.local` |

- Content scripts never hold a token. They message the service worker, which
  makes every API call. A token inside a content script is readable by page
  code on LinkedIn or ATS sites.
- Refresh token rotation with reuse detection: presenting an old refresh
  token revokes the whole token family and forces re-login.
- The server stores HMAC hashes with a server secret, not plain SHA-256.
- The dashboard lists connected browsers; revoking a device invalidates its
  whole family.

### 7.3 Scope: per-application, not global
- Device token: scope `extension:session` only — it can create apply sessions
  and nothing else. It cannot read resumes, applications, or the answer bank.
- Apply session token: `POST /api/extension/apply-sessions {application_id}`
  with the device token. The server checks: the application belongs to the
  device's user, status is `ready`, and no other live session exists for it.
  Returns a token valid for 10 minutes, bound to that application and device.
- Allowed operations, and nothing else:
  - `GET /api/applications/{id}/apply-payload`
  - `POST /api/applications/{id}/status` restricted to
    `ready -> submitted_pending_confirm` and `ready -> failed`
- The extension cannot set `applied`. The user confirms `applied` in the
  extension popup or the dashboard; the audit log records who confirmed.

### 7.4 The fragment carries no authority
- Preferred: "Open application" messages the extension (`externally_connectable`,
  platform origin only). The service worker opens apply_url itself and stores a
  `tabId -> applicationId` mapping in `chrome.storage.session`. No ID appears
  in the URL — any page script can read `location.hash`, and history and
  copied links keep it.
- Fallback without the extension: a plain apply_url tab. The user copies
  suggested answers manually, clicks Submit on the real site, then clicks
  "I applied" in the dashboard.

### 7.5 Hardening
- `externally_connectable` matches only the platform origin.
- Rate limit token endpoints and apply-session creation per device.
- Audit event on every session creation, status change, and revocation
  (`ApplicationEvent`).

### 7.6 Data model
ExtensionDevice(id, user, name, family_id, refresh_token_hash,
                created_at, last_used_at, revoked_at)
ApplySession(id, device, application, token_hash, expires_at, revoked_at)
Replaces the ExtensionToken table from earlier drafts.

## 8. Chrome extension (MV3)

- Permissions: storage, alarms. Host permissions only for the platform domain
  and supported ATS and LinkedIn job pages.
- No cookies permission. The extension never reads cookies.
- Auth: OAuth 2.0 + PKCE per section 7. Content scripts never hold tokens.
- Adapter interface:
    interface ApplyAdapter {
      detect(): boolean;
      fill(payload: ApplyPayload): FillResult;   // filled + needs_user_input
      detectSuccess(): boolean;
    }
- Adapter order: Greenhouse, Lever, Ashby, Workable, LinkedIn Easy Apply.
- Selectors live in a remote config so site changes do not need a Web Store release.
- Safety stop: on any CAPTCHA, verification, or "unusual activity" prompt,
  stop and notify the user.
- Testing: Playwright against saved page snapshots.

## 9. API (DRF)

Auth: JWT for the web app; OAuth 2.0 + PKCE (django-oauth-toolkit) for the
extension per section 7. MFA via allauth later.

POST   /api/oauth/...                         (authorize + token endpoints)
POST   /api/extension/apply-sessions          (device token -> per-application session)

POST   /api/auth/...                          (allauth endpoints)
POST   /api/resume/upload
GET    /api/resume/master
PUT    /api/resume/master
GET    /api/preferences
PUT    /api/preferences
GET    /api/inbox
POST   /api/applications/{id}/approve
POST   /api/applications/{id}/reject
GET    /api/applications/{id}/apply-payload   (PDF URL, answers, flags)
POST   /api/applications/{id}/status          (applied | failed, notes)
GET    /api/applications                      (tracker, filters)
GET    /api/answers
PUT    /api/answers
POST   /api/jobs/import-url
GET    /api/quota                             (today's cap and count)

## 10. Discovery sources and LinkedIn

- ATS APIs (primary): official public, unauthenticated job-board endpoints.
  Most stable source.
- JobSpy (MIT): supporting source for Indeed, Google, Naukri, Bayt.
- LinkedIn guest search (supplementary, ToS-gray): via JobSpy with proxies at
  volume. Treat as breakable. Failures never block other sources.
- LinkedIn Easy Apply: through the extension, inside the user's own browser,
  with the human clicking Submit.

Fact to keep in view: LinkedIn offers no official candidate job-search API.
Any LinkedIn discovery is unofficial.

Measurement (M6): scrape about 100 guest listings and record the Easy Apply
versus external share before expanding LinkedIn coverage.

## 11. Security, privacy, and data

- Resumes are personal data. Encrypt at rest, private buckets, short-lived
  signed URLs, per-user access checks on every endpoint.
- LLM data handling [VERIFY]: before beta, check the current Gemini API terms for
  free and paid tiers, especially whether submitted content can be used to improve
  Google's products. If it can, use the paid tier for user data.
- Disclosure: the privacy notice states that resume text is processed by Google's
  Gemini API.
- Retention: account deletion removes resumes, PDFs, and derived data. Inactive
  accounts are purged after 12 months, with notice. Job data is kept.
- Logging: log LLM calls without full resume text.
- Extension tokens: scoped, hashed, revocable.
- Rate limiting on all API endpoints. Upload validation (type, size).
- 2FA: planned. django-allauth MFA is enabled in a later milestone; the data
  model already has mfa_enabled.

## 12. Application limits

- Daily apply cap: drawn at random from the integer array [15..23], once per
  user per day, stored in DailyApplyLog, and shown to the user.
- Score threshold: platform default 70, user-adjustable.
- Per-user LLM quotas on the free tier to control cost.

## 13. Risks

| Risk | Mitigation |
|---|---|
| LinkedIn ToS and account restriction | Human submits; daily cap; plain disclosure; LinkedIn supplementary |
| Unofficial scraper breakage | ATS APIs primary; JobSpy isolated; non-blocking failures |
| Selector breakage in extension | Remote selector config; Playwright snapshot tests |
| Fabricated resume claims | Claims check blocks "ready"; user sees flags |
| Gemini data handling | Verify terms; paid tier for user data if needed; disclose |
| LLM cost growth | Two-stage scoring; caching; per-user quotas |
| Free-tier hosting limits | Plan paid upgrade at beta exit |
| Compromised extension token exposes user data | Device token creates sessions only; per-application 10-min tokens; refresh rotation with reuse detection |
| Pakistan boards not covered | Out of v1; custom adapters later |

## 14. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Repo scaffold: backend, web, extension, Docker Compose, CI | docker compose up runs; CI green |
| M1 | Job model, Greenhouse and Lever ingestion, Gemini scoring | One command prints top matches from 10 companies |
| M2 | Auth (allauth, MFA-ready), resume upload, parse via ResumeIQ, review screen | User signs up and sees parsed master resume |
| M3 | Inbox, approve or reject, preferences | Full review loop works in the web app |
| M4 | Tailoring, claims check, PDF rendering | Approved job yields a verified PDF |
| M5 | Apply page, tracker, reminders, answer bank, daily cap | Application prepared and tracked end to end |
| M6 | JobSpy, LinkedIn guest search, Easy Apply measurement | Share recorded; LinkedIn scope decided |
| M7 | Extension: Greenhouse and Lever adapters | Autofill and human submit work on both |
| M8 | Extension: Ashby, Workable, LinkedIn Easy Apply | Autofill works; cap enforced |
| M9 | Hardening: security review, monitoring, MFA, free-to-paid billing | Beta exit criteria met |

## 15. Open items

1. [CONFIRM] Email-apply path: mailto: link (assumed).
2. [CONFIRM] LLM provider: Gemini by default, bring-your-own-key later (assumed).
3. [CONFIRM] Retention: delete on request plus 12-month inactivity purge (assumed).
4. [CONFIRM] Score threshold: 70 default (assumed).
5. [CONFIRM] PDF renderer: RenderCV or WeasyPrint, after a 1-day test.
6. [CONFIRM] Hosting provider for the free beta.
7. [VERIFY] Gemini API terms for free and paid tiers on user data.
8. [VERIFY] ResumeIQ output shape and whether it maps to JSON Resume.
9. [VERIFY] Licenses of Resume-Matcher and ai-job-search before any code reuse.
10. [VERIFY] django-oauth-toolkit license (BSD-2-Clause, confirm) and fit with allauth MFA.
11. [VERIFY] Chrome Web Store review expectations for PKCE via launchWebAuthFlow and permission justifications.