# backend/jobs/tests/test_scoring.py
"""Tests for the scoring pipeline. All Gemini calls are mocked."""
import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from jobs.models import Application, Job, JobMatch, Profile
from jobs.services.scoring import (
    _parse_gemini_json,
    score_jobs_for_user,
)

User = get_user_model()

SAMPLE_RESUME = {
    "basics": {"name": "Jane Doe", "summary": "Full-stack developer with 5 years experience"},
    "skills": [
        {"name": "Python", "keywords": ["Django", "FastAPI"]},
        {"name": "JavaScript", "keywords": ["React", "TypeScript"]},
    ],
    "work": [
        {"name": "Acme Corp", "position": "Software Engineer", "summary": "Built APIs"},
    ],
    "education": [
        {"institution": "LUMS", "area": "Computer Science", "studyType": "BS"},
    ],
}

GOOD_GEMINI_RESPONSE = json.dumps({
    "llm_score": 85,
    "matched_skills": ["Python", "Django", "React"],
    "gaps": ["Go", "Kubernetes"],
    "rationale": "Strong match for backend role.",
})

BAD_GEMINI_RESPONSE = "This is not JSON at all {{{{"


@pytest.fixture
def user(db):
    return User.objects.create_user(email="test@example.com", password="pw12345!")


@pytest.fixture
def profile(user):
    return Profile.objects.create(user=user)


def make_job(description="Build awesome APIs with Python and Django", **kw):
    defaults = {
        "source": "linkedin",
        "external_id": kw.pop("external_id", "ext-1"),
        "title": "Software Engineer",
        "company_name": "TestCo",
        "location": "Karachi, Pakistan",
        "remote": False,
        "url": "http://example.com/job/1",
        "apply_url": "http://example.com/apply/1",
        "description": description,
        "fetched_at": timezone.now(),
        "status": "open",
    }
    defaults.update(kw)
    return Job.objects.create(**defaults)


class FakeEmbedResult:
    def __init__(self, values):
        self.values = values


class FakeEmbedResponse:
    def __init__(self):
        self.embeddings = [FakeEmbedResult([0.1] * 768)]


class FakeGenAIModels:
    """Mock for client.models that tracks call counts."""

    def __init__(self, responses=None, bad_then_good=False):
        self._responses = responses or [GOOD_GEMINI_RESPONSE]
        self._response_idx = 0
        self._bad_then_good = bad_then_good
        self.generate_calls = 0
        self.embed_calls = 0

    def embed_content(self, **kwargs):
        self.embed_calls += 1
        return FakeEmbedResponse()

    def generate_content(self, **kwargs):
        self.generate_calls += 1
        if self._bad_then_good and self.generate_calls == 1:
            resp = MagicMock()
            resp.text = BAD_GEMINI_RESPONSE
            return resp
        idx = min(self._response_idx, len(self._responses) - 1)
        self._response_idx += 1
        resp = MagicMock()
        resp.text = self._responses[idx]
        return resp


class FakeClient:
    def __init__(self, models_mock=None):
        self.models = models_mock or FakeGenAIModels()


def _run_scoring(user, jobs, client=None, top_n=20, threshold=70):
    """Helper: embed all jobs via raw SQL, then score."""
    from django.db import connection

    # Set a dummy embedding on each job so shortlist_by_embedding can find them
    vec_literal = "[" + ",".join(["0.1"] * 768) + "]"
    for job in jobs:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE jobs_job SET embedding = %s::vector WHERE id = %s",
                [vec_literal, job.id],
            )

    return score_jobs_for_user(
        user, SAMPLE_RESUME, resume_version=1,
        client=client, top_n=top_n, threshold=threshold,
    )


@pytest.mark.django_db(transaction=True)
def test_scoring_cache():
    """A second run makes zero Gemini LLM calls (cache hit)."""
    user = User.objects.create_user(email="cache@example.com", password="pw12345!")
    Profile.objects.create(user=user)
    job = make_job(external_id="cache-1")

    models_mock = FakeGenAIModels()
    client = FakeClient(models_mock)

    # First run: should call Gemini
    results1 = _run_scoring(user, [job], client=client)
    calls_after_first = models_mock.generate_calls
    assert calls_after_first > 0
    assert len(results1) == 1

    # Second run: should NOT call Gemini (cache hit)
    models_mock2 = FakeGenAIModels()
    client2 = FakeClient(models_mock2)
    results2 = _run_scoring(user, [job], client=client2)
    assert models_mock2.generate_calls == 0
    assert len(results2) == 1
    assert results2[0]["llm_score"] == results1[0]["llm_score"]


@pytest.mark.django_db(transaction=True)
def test_scoring_bad_json():
    """A bad Gemini response is retried once, then skipped without crashing."""
    user = User.objects.create_user(email="badjson@example.com", password="pw12345!")
    Profile.objects.create(user=user)
    job = make_job(external_id="bad-json-1")

    # Always returns bad JSON
    models_mock = FakeGenAIModels(responses=[BAD_GEMINI_RESPONSE])
    client = FakeClient(models_mock)

    results = _run_scoring(user, [job], client=client)
    # Should have tried twice (initial + 1 retry) then skipped
    assert models_mock.generate_calls == 2
    # No results because parsing failed
    assert len(results) == 0
    # No JobMatch created
    assert JobMatch.objects.filter(user=user, job=job).count() == 0


@pytest.mark.django_db(transaction=True)
def test_threshold():
    """Only jobs at or above the threshold become Application(status='inbox')."""
    user = User.objects.create_user(email="threshold@example.com", password="pw12345!")
    Profile.objects.create(user=user)

    job_above = make_job(external_id="above-1")
    job_below = make_job(external_id="below-1", description="Basic data entry role")

    # First job scores 85, second scores 40
    responses = [
        json.dumps({"llm_score": 85, "matched_skills": ["Python"], "gaps": [], "rationale": "Great"}),
        json.dumps({"llm_score": 40, "matched_skills": [], "gaps": ["All"], "rationale": "Poor"}),
    ]
    models_mock = FakeGenAIModels(responses=responses)
    client = FakeClient(models_mock)

    _run_scoring(user, [job_above, job_below], client=client, threshold=70)

    # Above threshold: should have Application
    assert Application.objects.filter(user=user, job=job_above, status="inbox").exists()
    # Below threshold: no Application
    assert not Application.objects.filter(user=user, job=job_below).exists()


@pytest.mark.django_db(transaction=True)
def test_no_description_skipped():
    """Jobs without a description are not scored."""
    user = User.objects.create_user(email="nodesc@example.com", password="pw12345!")
    Profile.objects.create(user=user)
    job_no_desc = make_job(external_id="no-desc-1", description="")
    job_with_desc = make_job(external_id="with-desc-1", description="Python developer needed")

    models_mock = FakeGenAIModels()
    client = FakeClient(models_mock)

    results = _run_scoring(user, [job_no_desc, job_with_desc], client=client)

    # Only the job with description should be scored
    scored_ids = {r["job_id"] for r in results}
    assert job_no_desc.id not in scored_ids
    assert job_with_desc.id in scored_ids


def test_parse_gemini_json_strips_fences():
    raw = '```json\n{"llm_score": 50}\n```'
    assert _parse_gemini_json(raw) == {"llm_score": 50}


def test_parse_gemini_json_plain():
    raw = '{"llm_score": 50}'
    assert _parse_gemini_json(raw) == {"llm_score": 50}


@pytest.mark.django_db(transaction=True)
def test_score_jobs_command(tmp_path, monkeypatch, capsys):
    """score_jobs management command prints a ranked table."""
    from django.core.management import call_command

    user = User.objects.create_user(email="cmd@example.com", password="pw12345!")
    Profile.objects.create(user=user)
    make_job(external_id="cmd-1", title="Backend Python Engineer", company_name="Acme")

    resume_file = tmp_path / "resume.json"
    resume_file.write_text(json.dumps(SAMPLE_RESUME))

    models_mock = FakeGenAIModels()
    fake_client = FakeClient(models_mock)
    monkeypatch.setattr("jobs.services.scoring._get_genai_client", lambda: fake_client)

    call_command("score_jobs", resume=str(resume_file), user="cmd@example.com", top=5)
    out = capsys.readouterr().out
    assert "Backend Python Engineer" in out
    assert "85" in out
    assert "Total: 1 jobs scored" in out
