import pytest
from django.utils import timezone

from jobs.models import Job, Profile, ScrapeLog
from jobs.services import budget
from jobs.services.descriptions import fill_descriptions
from jobs.services.filters import check_job
from jobs.sources.linkedin import LinkedInBlocked
from jobs.sources.linkedin_detail import fetch_description, parse_description

HTML = '<div class="show-more-less-html__markup"><p>Build APIs</p><ul><li>Python</li></ul></div>'


def test_parse_description():
    assert "Build APIs" in parse_description(HTML) and "Python" in parse_description(HTML)
    assert parse_description("<html></html>") == ""


def test_fetch_raises_on_429():
    class R:
        status_code = 429
        text = ""
    with pytest.raises(LinkedInBlocked):
        fetch_description("http://x", get=lambda *a, **k: R(), sleep=lambda s: None)


def test_require_description_switch():
    from types import SimpleNamespace as NS
    j = NS(title="Software Engineer", company_name="", location="Karachi", remote=False, description="")
    assert check_job(j, Profile()).reasons == ["no_description"]
    assert check_job(j, Profile(), require_description=False).passed


@pytest.mark.django_db
def test_budget_caps_fetches(settings):
    settings.LINKEDIN_MAX_DESCRIPTIONS_PER_DAY = 2
    for i in range(5):
        Job.objects.create(source="linkedin", external_id=str(i), title="Software Engineer",
                           location="Karachi", url=f"http://x/{i}", apply_url="", description="",
                           fetched_at=timezone.now())
    calls = []
    res = fill_descriptions(Profile(), fetch=lambda u: calls.append(u) or "desc")
    assert len(calls) == 2 and res["filled"] == 2 and budget.remaining("description") == 0
    assert ScrapeLog.objects.filter(kind="description").count() == 2
