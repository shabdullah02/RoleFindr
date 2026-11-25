# backend/jobs/services/scoring.py
"""
Slice 3 scoring pipeline:
  1. Embed resume + jobs with Gemini embeddings
  2. Shortlist top-N by cosine similarity (pgvector)
  3. Score shortlist with Gemini LLM (rubric prompt)
  4. Create JobMatch rows; promote above-threshold to Application(inbox)
"""
import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from jobs.models import Application, Job, JobMatch

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-004"
EMBED_DIM = 768
SCORE_MODEL = "gemini-2.5-flash"

RUBRIC_PROMPT = """\
You are a job-matching expert. Given a candidate's JSON Resume and a job description,
score how well the candidate fits the job.

Return ONLY valid JSON (no markdown fences, no extra text) with this exact structure:
{{
  "llm_score": <integer 0-100>,
  "matched_skills": [<list of strings>],
  "gaps": [<list of strings>],
  "rationale": "<one paragraph>"
}}

Scoring rubric:
- 90-100: Near-perfect match, all required skills present
- 70-89: Strong match, most skills present, minor gaps
- 50-69: Moderate match, some key skills missing
- 30-49: Weak match, significant gaps
- 0-29: Poor fit

## Candidate Resume (JSON Resume format)
{resume_json}

## Job Description
Title: {job_title}
Company: {company_name}
Location: {job_location}

{job_description}
"""


def _get_genai_client():
    """Lazy import to avoid import errors when google-genai is not installed."""
    from google import genai  # Apache-2.0

    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in settings / environment")
    return genai.Client(api_key=api_key)


@dataclass
class ScoringResult:
    llm_score: int
    matched_skills: list[str]
    gaps: list[str]
    rationale: str


def embed_text(text: str, *, client=None, task_type="RETRIEVAL_DOCUMENT") -> list[float]:
    """Get a Gemini embedding vector for a text string."""
    client = client or _get_genai_client()
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config={"task_type": task_type},
    )
    return result.embeddings[0].values


def embed_resume_text(json_resume: dict, *, client=None) -> list[float]:
    """Build a text representation of the JSON Resume and embed it."""
    parts = []
    basics = json_resume.get("basics", {})
    if basics.get("summary"):
        parts.append(basics["summary"])
    for sk in json_resume.get("skills", []):
        name = sk.get("name", "")
        keywords = ", ".join(sk.get("keywords", []))
        if name or keywords:
            parts.append(f"{name}: {keywords}" if keywords else name)
    for w in json_resume.get("work", []):
        line = f"{w.get('position', '')} at {w.get('name', '')}"
        if w.get("summary"):
            line += f" - {w['summary']}"
        parts.append(line)
    for e in json_resume.get("education", []):
        parts.append(f"{e.get('studyType', '')} {e.get('area', '')} at {e.get('institution', '')}")
    text = "\n".join(p for p in parts if p.strip())
    if not text:
        text = json.dumps(json_resume)[:2000]
    return embed_text(text, client=client, task_type="RETRIEVAL_DOCUMENT")


def embed_job_text(job: Job, *, client=None) -> list[float]:
    """Embed a job's description + title."""
    text = f"{job.title}\n{job.company_name}\n{job.location}\n\n{job.description}"
    return embed_text(text, client=client, task_type="RETRIEVAL_DOCUMENT")


def _parse_gemini_json(raw: str) -> dict:
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def score_job_with_llm(
    json_resume: dict,
    job: Job,
    *,
    client=None,
    model: str | None = None,
) -> ScoringResult:
    """Call Gemini with the rubric prompt. Returns parsed scoring result."""
    client = client or _get_genai_client()
    model = model or SCORE_MODEL

    prompt = RUBRIC_PROMPT.format(
        resume_json=json.dumps(json_resume, indent=2)[:8000],
        job_title=job.title,
        company_name=job.company_name or "",
        job_location=job.location or "",
        job_description=(job.description or "")[:6000],
    )

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    data = _parse_gemini_json(response.text)
    if not isinstance(data, dict):
        raise TypeError("Gemini response must be a JSON object")
    score = int(data["llm_score"])
    if not 0 <= score <= 100:
        raise ValueError(f"llm_score out of range: {score}")
    matched_skills = data.get("matched_skills", [])
    gaps = data.get("gaps", [])
    if not isinstance(matched_skills, list) or not isinstance(gaps, list):
        raise TypeError("matched_skills and gaps must be lists")
    return ScoringResult(
        llm_score=score,
        matched_skills=[str(s) for s in matched_skills],
        gaps=[str(g) for g in gaps],
        rationale=str(data.get("rationale", "")),
    )


def shortlist_by_embedding(
    resume_embedding: list[float],
    job_ids: list[int],
    top_n: int,
) -> list[tuple[int, float]]:
    """
    Use pgvector cosine distance to rank jobs.
    Returns list of (job_id, cosine_similarity) tuples.
    """
    from django.db import connection

    if not job_ids:
        return []

    vec_literal = "[" + ",".join(str(v) for v in resume_embedding) + "]"
    placeholders = ",".join(["%s"] * len(job_ids))

    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, 1 - (embedding <=> %s::vector) AS similarity
            FROM jobs_job
            WHERE id IN ({placeholders})
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [vec_literal] + list(job_ids) + [vec_literal, top_n],
        )
        return [(row[0], float(row[1])) for row in cur.fetchall()]


def score_jobs_for_user(
    user,
    json_resume: dict,
    resume_version: int,
    *,
    top_n: int | None = None,
    threshold: int | None = None,
    client=None,
    require_description: bool = True,
) -> list[dict[str, Any]]:
    """
    Full scoring pipeline for a user.
    Returns list of match dicts sorted by llm_score descending.
    """
    from jobs.services.filters import check_job

    top_n = top_n or getattr(settings, "SCORING_TOP_N", 20)
    client = client or _get_genai_client()

    # 1. Get user's profile (or empty defaults)
    from jobs.models import Profile
    from resumes.models import MasterResume

    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        profile = Profile(user=user)

    if threshold is None:
        threshold = getattr(profile, "score_threshold", None) or getattr(settings, "SCORING_THRESHOLD", 70)

    # 2. Find open jobs that pass hard filters
    open_jobs = Job.objects.filter(status=Job.Status.OPEN)
    if require_description:
        open_jobs = open_jobs.exclude(description="")
    candidate_ids = []
    for job in open_jobs.iterator():
        result = check_job(job, profile, require_description=require_description)
        if result.passed:
            candidate_ids.append(job.id)

    logger.info("score_jobs: %d jobs pass hard filters", len(candidate_ids))

    if not candidate_ids:
        return []

    # 3. Embed jobs that don't have embeddings yet
    jobs_without_embedding = Job.objects.filter(id__in=candidate_ids, embedding__isnull=True)
    for job in jobs_without_embedding.iterator():
        try:
            vec = embed_job_text(job, client=client)
            Job.objects.filter(id=job.id).update(embedding=vec)
            logger.info("score_jobs: embedded job_id=%d", job.id)
        except Exception:
            logger.exception("score_jobs: failed to embed job_id=%d", job.id)

    # 4. Embed the resume (store/reuse on MasterResume if present)
    master = MasterResume.objects.filter(user=user, version=resume_version).first()
    if master and master.embedding is not None:
        resume_vec = list(master.embedding)
    else:
        resume_vec = embed_resume_text(json_resume, client=client)
        if master:
            MasterResume.objects.filter(pk=master.pk).update(embedding=resume_vec)

    # 5. Shortlist by cosine similarity
    shortlist = shortlist_by_embedding(resume_vec, candidate_ids, top_n)
    logger.info("score_jobs: shortlisted %d jobs", len(shortlist))

    # 6. Score each shortlisted job with Gemini
    results = []
    gemini_calls = 0
    for job_id, embed_score in shortlist:
        # Cache check: skip if already scored for this resume version
        existing = JobMatch.objects.filter(
            user=user, job_id=job_id, resume_version=resume_version,
        ).first()
        if existing:
            logger.info("score_jobs: cache hit job_id=%d", job_id)
            results.append({
                "job_id": job_id,
                "embed_score": embed_score,
                "llm_score": existing.llm_score,
                "matched_skills": existing.matched_skills,
                "gaps": existing.gaps,
                "rationale": existing.rationale,
            })
            continue

        job = Job.objects.get(id=job_id)

        # Skip jobs without description
        if not (job.description or "").strip():
            logger.info("score_jobs: skipping job_id=%d (no description)", job_id)
            continue

        # Try scoring with Gemini, retry once on parse failure
        scoring = None
        for attempt in range(2):
            try:
                scoring = score_job_with_llm(json_resume, job, client=client)
                gemini_calls += 1
                break
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                gemini_calls += 1
                if attempt == 0:
                    logger.warning("score_jobs: bad JSON from Gemini for job_id=%d, retrying: %s", job_id, e)
                else:
                    logger.error("score_jobs: failed to parse Gemini response for job_id=%d after retry", job_id)
            except Exception as e:  # noqa: BLE001
                gemini_calls += 1
                logger.error("score_jobs: Gemini call failed for job_id=%d: %s", job_id, e)
                break

        if scoring is None:
            continue

        # Write JobMatch with update_or_create
        _match, _created = JobMatch.objects.update_or_create(
            user=user,
            job=job,
            resume_version=resume_version,
            defaults={
                "embed_score": embed_score,
                "llm_score": scoring.llm_score,
                "matched_skills": scoring.matched_skills,
                "gaps": scoring.gaps,
                "rationale": scoring.rationale,
                "scored_at": timezone.now(),
            },
        )

        results.append({
            "job_id": job_id,
            "embed_score": embed_score,
            "llm_score": scoring.llm_score,
            "matched_skills": scoring.matched_skills,
            "gaps": scoring.gaps,
            "rationale": scoring.rationale,
        })

        # Threshold: create Application(inbox) if above threshold
        if scoring.llm_score >= threshold:
            try:
                Application.objects.get_or_create(
                    user=user,
                    job=job,
                    defaults={"status": Application.Status.INBOX},
                )
            except IntegrityError:
                pass  # Already exists

    logger.info("score_jobs: %d Gemini calls made, %d results", gemini_calls, len(results))
    results.sort(key=lambda r: r.get("llm_score", 0) or 0, reverse=True)
    return results
